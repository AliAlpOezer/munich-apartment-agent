// Dashboard JSON API. Reads are open (protect the whole Worker with Cloudflare Access for privacy);
// writes need the API_TOKEN secret and fail closed when it is unset.

import { nextScheduledRun } from "./config";
import { startRun, type Deps } from "./pipeline";
import * as store from "./store";
import { TRIAGE_VALUES, type Triage } from "./types";
import { searchArea } from "./wggesucht";

const STALLED_AFTER_MS = 30 * 60 * 1000;
const REJECTED_WINDOW_MS = 14 * 86_400_000;

const json = (body: unknown, status = 200, headers: HeadersInit = {}) =>
  Response.json(body, { status, headers: { "cache-control": "no-store", ...headers } });
const fail = (status: number, error: string, headers: HeadersInit = {}) => json({ error }, status, headers);

async function tokenMatches(given: string, expected: string): Promise<boolean> {
  const enc = new TextEncoder();
  const a = enc.encode(given);
  const b = enc.encode(expected);
  // timingSafeEqual needs equal lengths; compare b to itself so the work does not leak the length.
  return a.byteLength === b.byteLength ? crypto.subtle.timingSafeEqual(a, b) : !crypto.subtle.timingSafeEqual(b, b);
}

async function authorize(req: Request, env: Env): Promise<Response | null> {
  if (!env.API_TOKEN) return fail(503, "Writes are disabled: set the API_TOKEN secret (wrangler secret put API_TOKEN).");
  const given = req.headers.get("x-api-token") ?? "";
  return (await tokenMatches(given, env.API_TOKEN)) ? null : fail(401, "Wrong or missing API token.");
}

export type RunStatus = "queued" | "running" | "done" | "failed" | "stalled";

export function runStatus(r: store.RunSummaryRow, now: Date): RunStatus {
  if (r.pages_failed > 0) return "failed";
  if (r.pages_total !== null && r.pages_done >= r.pages_total && r.pending === 0) return "done";
  const lastActivity = Date.parse(r.last_page_at ?? r.created_at);
  if (now.getTime() - lastActivity > STALLED_AFTER_MS) return "stalled";
  return r.pages_done === 0 ? "queued" : "running";
}

function listingJson(r: store.ListingRow) {
  return { ...r, reasons: JSON.parse(r.reasons) as string[], bike_detail: r.bike_detail ? JSON.parse(r.bike_detail) : null };
}

export async function handleApi(req: Request, env: Env, deps: Deps): Promise<Response> {
  const url = new URL(req.url);
  const path = url.pathname;
  const now = deps.now();

  if (req.method === "GET" && path === "/api/config") {
    return json({
      criteria: deps.settings.criteria,
      searchArea: searchArea(deps.settings.criteria),
      writesEnabled: Boolean(env.API_TOKEN),
    });
  }

  if (req.method === "GET" && path === "/api/listings") {
    const since = new Date(now.getTime() - REJECTED_WINDOW_MS).toISOString();
    const { active, rejected } = await store.listListings(deps.db, since);
    return json({ listings: active.map(listingJson), rejected: rejected.map(listingJson) });
  }

  if (req.method === "GET" && path === "/api/runs") {
    const runs = await store.runSummaries(deps.db, 20);
    return json({
      runs: runs.map((r) => ({ ...r, status: runStatus(r, now) })),
      nextRunAt: nextScheduledRun(now).toISOString(),
    });
  }

  if (req.method === "POST" && path === "/api/run") {
    const denied = await authorize(req, env);
    if (denied) return denied;
    const last = await store.lastRunCreatedAt(deps.db);
    const cooldownMs = deps.settings.manualRunCooldownMinutes * 60_000;
    const waitMs = last ? Date.parse(last) + cooldownMs - now.getTime() : 0;
    if (waitMs > 0) {
      const seconds = Math.ceil(waitMs / 1000);
      return fail(429, `A run started recently; try again in ${Math.ceil(seconds / 60)} min.`, { "retry-after": String(seconds) });
    }
    return json({ runId: await startRun(deps, "manual") }, 202);
  }

  const triageMatch = /^\/api\/listings\/(\d+)\/triage$/.exec(path);
  if (req.method === "POST" && triageMatch) {
    const denied = await authorize(req, env);
    if (denied) return denied;
    const body = (await req.json().catch(() => null)) as { triage?: unknown } | null;
    const triage = body?.triage;
    if (typeof triage !== "string" || !TRIAGE_VALUES.includes(triage as Triage)) {
      return fail(400, `triage must be one of ${TRIAGE_VALUES.join(", ")}`);
    }
    const ok = await store.setTriage(deps.db, Number(triageMatch[1]), triage as Triage);
    return ok ? json({ ok: true }) : fail(404, "No such listing.");
  }

  return fail(404, "Not found.");
}
