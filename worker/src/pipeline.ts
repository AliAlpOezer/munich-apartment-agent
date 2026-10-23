// Run stages as queue jobs: search page -> (new or re-decided candidates) -> detail page. A run walks
// one result list per search stream (a source category); every handler is idempotent, so
// at-least-once delivery and overlapping runs are harmless.

import { bikeTimes, type Fetcher, type Point } from "./bike";
import type { Settings } from "./config";
import { evaluate } from "./filter";
import { LEGACY_STREAM, sourceById, sourceOfStream } from "./registry";
import { isOnOrigin, ListingGone, type DetailFacts, type Source } from "./sources";
import * as store from "./store";
import type { BikeTime, Job, ListingFacts, ScrapedListing } from "./types";

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
// Spacing between queued fetches, so a run never bursts requests at a source.
const PAGE_SPACING_S = 5;
const DETAIL_SPACING_S = 3;
const STALE_PENDING_MS = 60 * 60 * 1000;
// Bump when a rule in filter.ts changes meaning, so listings still online are re-decided.
const RULES_REVISION = 2;

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

/** Short hash of the criteria and the rules revision. A listing decided under another version is
 *  re-decided the next time it shows up on a search page, so changing a limit or a rule applies to
 *  everything still online. */
export async function criteriaVersion(c: Settings["criteria"]): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify({ rules: RULES_REVISION, ...c }));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].slice(0, 8).map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Calendar day in Munich: availability dates on the sites are local. */
export function berlinDay(d: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Berlin" }).format(d);
}

export async function startRun(deps: Deps, trigger: "cron" | "manual"): Promise<string> {
  const { db, jobs, settings } = deps;
  const now = deps.now();
  const nowIso = now.toISOString();
  const runId = crypto.randomUUID();
  await store.createRun(db, runId, trigger, settings.criteria, nowIso);

  const stale = await store.stalePendingIds(db, new Date(now.getTime() - STALE_PENDING_MS).toISOString());
  if (stale.length) {
    await jobs.sendBatch(stale.map((listingId, i) => ({
      body: { kind: "detail", runId, listingId }, delaySeconds: i * DETAIL_SPACING_S,
    })));
  }
  const streams = settings.sources.flatMap((s) => s.streams(settings.criteria));
  for (const { stream } of streams) await store.claimPages(db, runId, stream, [0], nowIso);
  await jobs.sendBatch(streams.map(({ stream, url }, i) => ({
    body: { kind: "search", runId, stream, page: 0, url }, delaySeconds: i * PAGE_SPACING_S,
  })));
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

/** The facts the filter reads, but the ride. Facts a source only has on its detail page come from
 *  the stored row, so a re-decision from the card never forgets them. */
function cardFacts(
  listing: ScrapedListing, source: Source, known: store.KnownListing | undefined,
): { listing: ScrapedListing; facts: ListingFacts; detailDone: boolean } {
  const merged = { ...listing, swap: listing.swap || known?.swap === 1 };
  if (known && source.detailOnly.position) Object.assign(merged, { lat: known.lat, lng: known.lng });
  if (known && source.detailOnly.availability) {
    Object.assign(merged, { availableFrom: known.available_from, availableTo: known.available_to });
  }
  const detailDone = known?.detail_status === "ok";
  return {
    listing: merged,
    detailDone,
    facts: {
      priceListed: merged.priceListed,
      priceWarm: detailDone ? known.price_warm : null,
      priceCold: detailDone ? known.price_cold : null,
      sizeSqm: merged.sizeSqm, availableFrom: merged.availableFrom, availableTo: merged.availableTo,
      bikeMinutes: null, stopMinutes: null, swap: merged.swap,
    },
  };
}

async function handleSearchPage(
  job: Extract<Job, { kind: "search" }>, attempts: number, deps: Deps,
): Promise<Outcome> {
  const { db, jobs, settings, fetcher } = deps;
  const { criteria } = settings;
  const stream = job.stream ?? LEGACY_STREAM;
  const source = sourceOfStream(stream);
  const nowIso = () => deps.now().toISOString();
  const record = (status: "done" | "failed", cards: number, error: string | null) =>
    store.recordPage(db, job.runId, stream, job.page, status, cards, error, nowIso());

  if (!source || !isOnOrigin(job.url, source.origin)) {
    await record("failed", 0, `refused URL ${job.url}`);
    return ACK;
  }

  let page: Awaited<ReturnType<Source["parseSearchPage"]>>;
  try {
    page = await source.parseSearchPage(await fetchPage(job.url, fetcher), job.url);
  } catch (e) {
    const retry = retryOrGiveUp(attempts);
    if (retry) return retry;
    await record("failed", 0, `fetch failed: ${errorText(e)}`);
    return ACK;
  }

  if (page.listings.length === 0 && !page.zeroResults) {
    // Success is observed, not assumed: a 200 page with no parseable cards is a layout change.
    await record("failed", 0, `0 cards parsed (${page.emptyHint}) - did the page layout change?`);
    return ACK;
  }

  // Extend the frontier: every linked page below the cap that no page of this run has claimed yet.
  const linked = [...page.pageUrls].filter(([n]) => n < settings.maxPages);
  const claimed = await store.claimPages(db, job.runId, stream, linked.map(([n]) => n), nowIso());
  if (claimed.length) {
    const urls = new Map(linked);
    await jobs.sendBatch(claimed.map((n, i) => ({
      body: { kind: "search", runId: job.runId, stream, page: n, url: urls.get(n)! },
      delaySeconds: (i + 1) * PAGE_SPACING_S,
    })));
  }

  const ids = page.listings.map((l) => l.externalId);
  const known = await store.knownListings(db, source.id, ids);
  const version = await criteriaVersion(criteria);
  // Decide first sightings, and re-decide sightings whose decision predates the current criteria or
  // rests on an estimated ride (estimates are provisional until the router answers). A pending row
  // is mid-decision under the current rules and is left alone.
  const toDecide = page.listings.filter((l) => {
    const k = known.get(l.externalId);
    if (!k) return true;
    return k.stage !== "pending_detail" && (k.criteria_version !== version || k.bike_source === "estimate");
  });
  const drafts = toDecide.map((l) => {
    const k = known.get(l.externalId);
    return { k, ...cardFacts(l, source, k) };
  });
  const { times, routerError } = await bikeTimes(
    drafts.map(({ listing: l }) => (l.lat !== null && l.lng !== null ? { lat: l.lat, lng: l.lng } : null)),
    criteria.anchors, criteria.transitStops, criteria.bikeSpeedKmh, settings.routerUrl, fetcher,
  );
  if (routerError) console.warn(`router unavailable, using estimates: ${routerError}`);

  const today = berlinDay(deps.now());
  const fresh: store.Decision[] = [];
  const redecided: (store.Decision & { id: number })[] = [];
  drafts.forEach(({ k, listing, facts, detailDone }, i) => {
    const bike = times[i];
    const verdict = evaluate(
      { ...facts, bikeMinutes: bike?.minutes ?? null, stopMinutes: bike?.stop?.minutes ?? null }, criteria, today,
    );
    const stage = !verdict.matched ? "rejected" : detailDone ? "matched" : "pending_detail";
    const decision = { listing, bike, stage, reasons: verdict.reasons } as const;
    if (k) redecided.push({ ...decision, id: k.id });
    else fresh.push(decision);
  });
  const untouched = ids.filter((id) => known.has(id) && !toDecide.some((l) => l.externalId === id));

  const now = nowIso();
  await store.saveSearchResults(db, source.id, job.runId, now, version, fresh, redecided, untouched);
  // A router outage doesn't fail the page, but it must be visible in the run history.
  await record("done", page.listings.length, routerError ? `router unavailable (${routerError}), rides estimated` : null);

  const pending = await store.pendingDetailIds(db, source.id, ids);
  if (pending.length) {
    await jobs.sendBatch(pending.map((listingId, i) => ({
      body: { kind: "detail", runId: job.runId, listingId }, delaySeconds: i * DETAIL_SPACING_S,
    })));
  }
  return ACK;
}

const samePoint = (row: store.ListingRow, p: Point) => row.lat === p.lat && row.lng === p.lng;

async function handleDetail(
  job: Extract<Job, { kind: "detail" }>, attempts: number, deps: Deps,
): Promise<Outcome> {
  const { db, settings, fetcher } = deps;
  const { criteria } = settings;
  const row = await store.getListing(db, job.listingId);
  if (!row || row.stage !== "pending_detail") return ACK; // already decided: redelivery is a no-op

  const source = sourceById(row.source);
  let detail: DetailFacts = { warm: null, cold: null };
  let detailStatus: "ok" | "failed" = "failed";
  let gone = false;
  if (source && isOnOrigin(row.url, source.origin)) {
    try {
      detail = await source.parseDetail(await fetchPage(row.url, fetcher), row.url);
      detailStatus = "ok";
    } catch (e) {
      gone = e instanceof ListingGone || (e instanceof HttpError && (e.status === 404 || e.status === 410));
      if (!gone) {
        const retry = retryOrGiveUp(attempts);
        if (retry) return retry;
        console.warn(`detail ${row.source}/${row.external_id} failed, deciding on card facts: ${errorText(e)}`);
      }
    }
  }

  // Route a position the card did not have (or that moved), unless the stored ride is already routed.
  const position = detail.position ?? null;
  let bike: BikeTime | null = null;
  if (position && !(samePoint(row, position) && row.bike_source === "valhalla")) {
    const { times, routerError } = await bikeTimes(
      [position], criteria.anchors, criteria.transitStops, criteria.bikeSpeedKmh, settings.routerUrl, fetcher,
    );
    if (routerError) console.warn(`router unavailable, using an estimate: ${routerError}`);
    bike = times[0];
  }

  const swap = row.swap === 1 || detail.swap === true;
  const verdict = evaluate(
    {
      priceListed: row.price_listed, priceWarm: detail.warm, priceCold: detail.cold,
      sizeSqm: row.size_sqm ?? detail.sizeSqm ?? null,
      availableFrom: detail.availableFrom ?? row.available_from, availableTo: row.available_to,
      bikeMinutes: bike ? bike.minutes : row.bike_minutes,
      stopMinutes: bike ? (bike.stop?.minutes ?? null) : row.stop_minutes,
      swap,
    },
    criteria,
    berlinDay(deps.now()),
  );
  const reasons = gone ? ["listing no longer online"] : verdict.reasons;
  await store.decideListing(db, row.id, {
    priceWarm: detail.warm, priceCold: detail.cold, stage: !gone && verdict.matched ? "matched" : "rejected",
    reasons, detailStatus, criteriaVersion: await criteriaVersion(criteria), now: deps.now().toISOString(),
    detail: {
      position: bike ? position : null, bike, availableFrom: detail.availableFrom ?? null,
      sizeSqm: detail.sizeSqm ?? null, swap,
    },
  });
  return ACK;
}
