// Every SQL statement lives here. The pipeline writes facts and stage; only setTriage writes triage.

import type { BikeTime, ScrapedListing, Stage, Triage } from "./types";

const MAX_PARAMS = 90; // D1 allows 100 bound parameters per statement

export interface ListingRow {
  id: number;
  source: string;
  external_id: string;
  url: string;
  title: string | null;
  listing_type: string;
  kind_label: string | null;
  place: string | null;
  street: string | null;
  lat: number | null;
  lng: number | null;
  price_listed: number | null;
  price_warm: number | null;
  price_cold: number | null;
  size_sqm: number | null;
  available_from: string | null;
  available_to: string | null;
  bike_minutes: number | null;
  bike_km: number | null;
  bike_source: BikeTime["source"] | null;
  bike_detail: string | null;
  stage: Stage;
  reasons: string;
  detail_status: "ok" | "failed" | null;
  triage: Triage;
  first_seen_run: string;
  last_seen_run: string;
  first_seen_at: string;
  last_seen_at: string;
  decided_at: string | null;
}

export async function createRun(
  db: D1Database, id: string, trigger: "cron" | "manual", criteria: unknown, now: string,
): Promise<void> {
  await db
    .prepare("INSERT INTO runs (id, trigger, created_at, criteria) VALUES (?, ?, ?, ?)")
    .bind(id, trigger, now, JSON.stringify(criteria))
    .run();
}

export async function lastRunCreatedAt(db: D1Database): Promise<string | null> {
  return db.prepare("SELECT MAX(created_at) AS at FROM runs").first<string>("at");
}

export async function pagesTotal(db: D1Database, runId: string): Promise<number | null> {
  return db.prepare("SELECT pages_total FROM runs WHERE id = ?").bind(runId).first<number>("pages_total");
}

export async function setPagesTotal(db: D1Database, runId: string, total: number): Promise<void> {
  await db
    .prepare("UPDATE runs SET pages_total = ? WHERE id = ? AND pages_total IS NULL")
    .bind(total, runId)
    .run();
}

export async function recordPage(
  db: D1Database, runId: string, page: number, status: "done" | "failed", cards: number,
  error: string | null, now: string,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO run_pages (run_id, page, status, cards, error, finished_at) VALUES (?, ?, ?, ?, ?, ?)
       ON CONFLICT (run_id, page) DO UPDATE SET
         status = excluded.status, cards = excluded.cards, error = excluded.error,
         finished_at = excluded.finished_at`,
    )
    .bind(runId, page, status, cards, error, now)
    .run();
}

function chunks<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

export async function existingIds(db: D1Database, source: string, ids: string[]): Promise<Set<string>> {
  const found = new Set<string>();
  for (const part of chunks(ids, MAX_PARAMS)) {
    const { results } = await db
      .prepare(
        `SELECT external_id FROM listings WHERE source = ? AND external_id IN (${part.map(() => "?").join(",")})`,
      )
      .bind(source, ...part)
      .all<{ external_id: string }>();
    for (const r of results) found.add(r.external_id);
  }
  return found;
}

export interface NewListing {
  listing: ScrapedListing;
  bike: BikeTime | null;
  stage: Stage;
  reasons: string[];
}

/** Insert first sightings and touch re-sightings in one transaction. A conflicting insert (the row
 *  appeared since `existingIds`) only touches last_seen, so a stage is never overwritten. */
export async function saveSearchResults(
  db: D1Database, source: string, runId: string, now: string, fresh: NewListing[], seenAgain: string[],
): Promise<void> {
  const insert = db.prepare(
    `INSERT INTO listings (source, external_id, url, title, listing_type, kind_label, place, street,
       lat, lng, price_listed, size_sqm, available_from, available_to,
       bike_minutes, bike_km, bike_source, bike_detail, stage, reasons,
       first_seen_run, last_seen_run, first_seen_at, last_seen_at, decided_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT (source, external_id) DO UPDATE SET
       last_seen_run = excluded.last_seen_run, last_seen_at = excluded.last_seen_at`,
  );
  const touch = db.prepare(
    "UPDATE listings SET last_seen_run = ?, last_seen_at = ? WHERE source = ? AND external_id = ?",
  );
  const statements = [
    ...fresh.map(({ listing: l, bike, stage, reasons }) =>
      insert.bind(
        source, l.externalId, l.url, l.title, l.listingType, l.kindLabel, l.place, l.street,
        l.lat, l.lng, l.priceListed, l.sizeSqm, l.availableFrom, l.availableTo,
        bike?.minutes ?? null, bike?.km ?? null, bike?.source ?? null,
        bike ? JSON.stringify(bike.perAnchor) : null, stage, JSON.stringify(reasons),
        runId, runId, now, now, stage === "rejected" ? now : null,
      ),
    ),
    ...seenAgain.map((id) => touch.bind(runId, now, source, id)),
  ];
  if (statements.length) await db.batch(statements);
}

/** Listings from this page that this run first saw and that still await their detail page. */
export async function pendingDetailIds(
  db: D1Database, source: string, runId: string, externalIds: string[],
): Promise<number[]> {
  const out: number[] = [];
  for (const part of chunks(externalIds, MAX_PARAMS)) {
    const { results } = await db
      .prepare(
        `SELECT id FROM listings WHERE source = ? AND first_seen_run = ? AND stage = 'pending_detail'
           AND external_id IN (${part.map(() => "?").join(",")})`,
      )
      .bind(source, runId, ...part)
      .all<{ id: number }>();
    out.push(...results.map((r) => r.id));
  }
  return out;
}

/** Pending rows whose detail message was lost (e.g. queue retention expired). */
export async function stalePendingIds(db: D1Database, olderThan: string): Promise<number[]> {
  const { results } = await db
    .prepare("SELECT id FROM listings WHERE stage = 'pending_detail' AND first_seen_at < ? LIMIT 50")
    .bind(olderThan)
    .all<{ id: number }>();
  return results.map((r) => r.id);
}

export async function getListing(db: D1Database, id: number): Promise<ListingRow | null> {
  return db.prepare("SELECT * FROM listings WHERE id = ?").bind(id).first<ListingRow>();
}

/** The only stage transition: pending_detail -> matched | rejected. Returns false if it already
 *  happened (redelivered message), so a decision is never made twice. */
export async function decideListing(
  db: D1Database, id: number,
  d: { priceWarm: number | null; priceCold: number | null; stage: Exclude<Stage, "pending_detail">;
       reasons: string[]; detailStatus: "ok" | "failed"; now: string },
): Promise<boolean> {
  const res = await db
    .prepare(
      `UPDATE listings SET price_warm = ?, price_cold = ?, stage = ?, reasons = ?, detail_status = ?,
         decided_at = ?
       WHERE id = ? AND stage = 'pending_detail'`,
    )
    .bind(d.priceWarm, d.priceCold, d.stage, JSON.stringify(d.reasons), d.detailStatus, d.now, id)
    .run();
  return res.meta.changes === 1;
}

export async function setTriage(db: D1Database, id: number, triage: Triage): Promise<boolean> {
  const res = await db.prepare("UPDATE listings SET triage = ? WHERE id = ?").bind(triage, id).run();
  return res.meta.changes === 1;
}

export async function listListings(
  db: D1Database, rejectedSince: string,
): Promise<{ active: ListingRow[]; rejected: ListingRow[] }> {
  const [active, rejected] = await db.batch<ListingRow>([
    db.prepare("SELECT * FROM listings WHERE stage != 'rejected' ORDER BY first_seen_at DESC, id DESC LIMIT 1000"),
    db
      .prepare(
        "SELECT * FROM listings WHERE stage = 'rejected' AND first_seen_at >= ? ORDER BY first_seen_at DESC, id DESC LIMIT 300",
      )
      .bind(rejectedSince),
  ]);
  return { active: active.results, rejected: rejected.results };
}

export interface RunSummaryRow {
  id: string;
  trigger: "cron" | "manual";
  created_at: string;
  pages_total: number | null;
  pages_done: number;
  pages_failed: number;
  errors: string | null;
  last_page_at: string | null;
  scraped: number;
  new: number;
  matched: number;
  pending: number;
}

export async function runSummaries(db: D1Database, limit: number): Promise<RunSummaryRow[]> {
  const { results } = await db
    .prepare(
      `SELECT r.id, r.trigger, r.created_at, r.pages_total,
         (SELECT COUNT(*) FROM run_pages p WHERE p.run_id = r.id) AS pages_done,
         (SELECT COUNT(*) FROM run_pages p WHERE p.run_id = r.id AND p.status = 'failed') AS pages_failed,
         (SELECT group_concat('page ' || p.page || ': ' || p.error, '; ') FROM run_pages p
            WHERE p.run_id = r.id AND p.error IS NOT NULL) AS errors,
         (SELECT MAX(p.finished_at) FROM run_pages p WHERE p.run_id = r.id) AS last_page_at,
         (SELECT COALESCE(SUM(p.cards), 0) FROM run_pages p WHERE p.run_id = r.id) AS scraped,
         (SELECT COUNT(*) FROM listings l WHERE l.first_seen_run = r.id) AS new,
         (SELECT COUNT(*) FROM listings l WHERE l.first_seen_run = r.id AND l.stage = 'matched') AS matched,
         (SELECT COUNT(*) FROM listings l WHERE l.first_seen_run = r.id AND l.stage = 'pending_detail') AS pending
       FROM runs r ORDER BY r.created_at DESC LIMIT ?`,
    )
    .bind(limit)
    .all<RunSummaryRow>();
  return results;
}
