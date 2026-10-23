// Run stages as queue jobs: search page -> (new candidates) -> detail page. Every handler is
// idempotent, so at-least-once delivery and overlapping runs are harmless.

import { bikeTimes, type Fetcher } from "./bike";
import type { Settings } from "./config";
import { evaluate } from "./filter";
import * as store from "./store";
import type { Job, ListingFacts } from "./types";
import { buildSearchUrl, isSourceUrl, parseDetailCosts, parseSearchPage, SOURCE } from "./wggesucht";

export interface Deps {
  db: D1Database;
  jobs: Queue<Job>;
  fetcher: Fetcher;
  settings: Settings;
  now: () => Date;
}

/** Fetch failures are retried by the handler with backoff; the last attempt records the failure. */
export const MAX_FETCH_ATTEMPTS = 3;
const RETRY_DELAYS_S = [60, 300];
// Spacing between queued fetches, so a run never bursts requests at the source.
const PAGE_SPACING_S = 5;
const DETAIL_SPACING_S = 3;
const STALE_PENDING_MS = 60 * 60 * 1000;

const BROWSER_HEADERS = {
  accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  "accept-language": "de-DE,de;q=0.9,en;q=0.8",
  "user-agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
};

export type Outcome = { ack: true } | { ack: false; retryAfterSeconds: number };
const ACK: Outcome = { ack: true };

export class HttpError extends Error {
  constructor(readonly status: number, url: string) {
    super(`HTTP ${status} for ${url}`);
  }
}

async function fetchPage(url: string, fetcher: Fetcher): Promise<Response> {
  const res = await fetcher(url, { headers: BROWSER_HEADERS, signal: AbortSignal.timeout(20_000) });
  if (!res.ok) throw new HttpError(res.status, url);
  return res;
}

const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Calendar day in Munich: availability dates on the site are local. */
export function berlinDay(d: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Berlin" }).format(d);
}

export async function startRun(deps: Deps, trigger: "cron" | "manual"): Promise<string> {
  const { db, jobs, settings } = deps;
  const now = deps.now();
  const runId = crypto.randomUUID();
  await store.createRun(db, runId, trigger, settings.criteria, now.toISOString());

  const stale = await store.stalePendingIds(db, new Date(now.getTime() - STALE_PENDING_MS).toISOString());
  if (stale.length) {
    await jobs.sendBatch(stale.map((listingId, i) => ({
      body: { kind: "detail", runId, listingId }, delaySeconds: i * DETAIL_SPACING_S,
    })));
  }
  await jobs.send({ kind: "search", runId, page: 0, url: buildSearchUrl(settings.criteria) });
  return runId;
}

export async function handleJob(job: Job, attempts: number, deps: Deps): Promise<Outcome> {
  return job.kind === "search" ? handleSearchPage(job, attempts, deps) : handleDetail(job, attempts, deps);
}

function retryOrGiveUp(attempts: number): Outcome | null {
  return attempts < MAX_FETCH_ATTEMPTS
    ? { ack: false, retryAfterSeconds: RETRY_DELAYS_S[Math.min(attempts - 1, RETRY_DELAYS_S.length - 1)] }
    : null;
}

async function handleSearchPage(
  job: Extract<Job, { kind: "search" }>, attempts: number, deps: Deps,
): Promise<Outcome> {
  const { db, jobs, settings, fetcher } = deps;
  const { criteria } = settings;
  const nowIso = () => deps.now().toISOString();

  if (!isSourceUrl(job.url)) {
    await store.recordPage(db, job.runId, job.page, "failed", 0, `refused URL ${job.url}`, nowIso());
    return ACK;
  }

  let html: string;
  try {
    html = await (await fetchPage(job.url, fetcher)).text();
  } catch (e) {
    const retry = retryOrGiveUp(attempts);
    if (retry) return retry;
    await store.recordPage(db, job.runId, job.page, "failed", 0, `fetch failed: ${errorText(e)}`, nowIso());
    return ACK;
  }

  const page = await parseSearchPage(html);
  if (page.listings.length === 0 && !page.zeroResults) {
    // Success is observed, not assumed: a 200 page with no parseable cards is a layout change.
    const why = `0 cards parsed (${page.markerCount} map markers) - did the page layout change?`;
    await store.recordPage(db, job.runId, job.page, "failed", 0, why, nowIso());
    return ACK;
  }

  if (job.page === 0 && (await store.pagesTotal(db, job.runId)) === null) {
    const more = [...page.pageUrls].filter(([n]) => n < settings.maxPages).sort(([a], [b]) => a - b);
    if (more.length) {
      await jobs.sendBatch(more.map(([n, url], i) => ({
        body: { kind: "search", runId: job.runId, page: n, url }, delaySeconds: (i + 1) * PAGE_SPACING_S,
      })));
    }
    await store.setPagesTotal(db, job.runId, 1 + more.length);
  }

  const ids = page.listings.map((l) => l.externalId);
  const known = await store.existingIds(db, SOURCE, ids);
  const fresh = page.listings.filter((l) => !known.has(l.externalId));
  const { times, routerError } = await bikeTimes(
    fresh.map((l) => (l.lat !== null && l.lng !== null ? { lat: l.lat, lng: l.lng } : null)),
    criteria.anchors, criteria.bikeSpeedKmh, settings.routerUrl, fetcher,
  );
  if (routerError) console.warn(`router unavailable, using estimates: ${routerError}`);

  const today = berlinDay(deps.now());
  const decided = fresh.map((listing, i) => {
    const bike = times[i];
    const facts: ListingFacts = {
      priceListed: listing.priceListed, priceWarm: null, priceCold: null, sizeSqm: listing.sizeSqm,
      availableFrom: listing.availableFrom, availableTo: listing.availableTo,
      bikeMinutes: bike?.minutes ?? null,
    };
    const verdict = evaluate(facts, criteria, today);
    return { listing, bike, stage: verdict.matched ? "pending_detail" : "rejected", reasons: verdict.reasons } as const;
  });

  const now = nowIso();
  await store.saveSearchResults(db, SOURCE, job.runId, now, decided, [...known]);
  await store.recordPage(db, job.runId, job.page, "done", page.listings.length, null, now);

  const pending = await store.pendingDetailIds(db, SOURCE, job.runId, ids);
  if (pending.length) {
    await jobs.sendBatch(pending.map((listingId, i) => ({
      body: { kind: "detail", runId: job.runId, listingId }, delaySeconds: i * DETAIL_SPACING_S,
    })));
  }
  return ACK;
}

async function handleDetail(
  job: Extract<Job, { kind: "detail" }>, attempts: number, deps: Deps,
): Promise<Outcome> {
  const { db, settings, fetcher } = deps;
  const row = await store.getListing(db, job.listingId);
  if (!row || row.stage !== "pending_detail") return ACK; // already decided: redelivery is a no-op

  let warm: number | null = null;
  let cold: number | null = null;
  let detailStatus: "ok" | "failed" = "failed";
  let gone = false;
  if (isSourceUrl(row.url)) {
    try {
      ({ warm, cold } = await parseDetailCosts(await fetchPage(row.url, fetcher)));
      detailStatus = "ok";
    } catch (e) {
      gone = e instanceof HttpError && (e.status === 404 || e.status === 410);
      if (!gone) {
        const retry = retryOrGiveUp(attempts);
        if (retry) return retry;
        console.warn(`detail ${row.external_id} failed, deciding on card facts: ${errorText(e)}`);
      }
    }
  }

  const verdict = evaluate(
    {
      priceListed: row.price_listed, priceWarm: warm, priceCold: cold, sizeSqm: row.size_sqm,
      availableFrom: row.available_from, availableTo: row.available_to, bikeMinutes: row.bike_minutes,
    },
    settings.criteria,
    berlinDay(deps.now()),
  );
  const reasons = gone ? ["listing no longer online"] : verdict.reasons;
  await store.decideListing(db, row.id, {
    priceWarm: warm, priceCold: cold, stage: !gone && verdict.matched ? "matched" : "rejected",
    reasons, detailStatus, now: deps.now().toISOString(),
  });
  return ACK;
}
