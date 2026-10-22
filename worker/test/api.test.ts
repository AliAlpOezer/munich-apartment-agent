import { env, exports as workerExports } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import { handleApi, runStatus } from "../src/api";
import * as store from "../src/store";
import { deps, fakeFetcher, fakeQueue } from "./helpers";

const NOW = new Date("2026-10-22T12:00:00Z");
const call = (path: string, init: RequestInit = {}, e: Env = env, q = fakeQueue()) =>
  handleApi(new Request(`https://agent.test${path}`, init), e, deps(fakeFetcher({}), q, NOW));
const post = (body?: unknown, token: string | null = "test-token") =>
  ({
    method: "POST",
    headers: { "content-type": "application/json", ...(token ? { "x-api-token": token } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  }) satisfies RequestInit;

beforeEach(async () => {
  await env.DB.batch([
    env.DB.prepare("DELETE FROM listings"),
    env.DB.prepare("DELETE FROM run_pages"),
    env.DB.prepare("DELETE FROM runs"),
  ]);
});

async function seedListing(): Promise<number> {
  await store.createRun(env.DB, "r0", "cron", {}, "2026-10-22T10:00:00Z");
  await store.saveSearchResults(env.DB, "wg_gesucht", "r0", "2026-10-22T10:00:00Z", [{
    listing: {
      externalId: "1", url: "https://www.wg-gesucht.de/x.1.html", title: "Room", listingType: "wg_room",
      kindLabel: "3er WG", place: "Garching", street: null, lat: 48.25, lng: 11.65, priceListed: 600,
      sizeSqm: 14, availableFrom: "2026-11-01", availableTo: null,
    },
    bike: { minutes: 12, km: 4, source: "valhalla", perAnchor: [{ label: "TUM", minutes: 12, km: 4 }] },
    stage: "pending_detail",
    reasons: [],
  }], []);
  return (await env.DB.prepare("SELECT id FROM listings").first<number>("id"))!;
}

describe("reads", () => {
  it("exposes the criteria and whether writes are enabled", async () => {
    const res = await call("/api/config");
    const body = await res.json<{ criteria: { maxWarmRentEur: number }; searchArea: { radiusM: number }; writesEnabled: boolean }>();
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(body.criteria.maxWarmRentEur).toBe(650);
    expect(body.searchArea.radiusM).toBe(11300);
    expect(body.writesEnabled).toBe(true);
  });

  it("lists listings with JSON columns decoded", async () => {
    await seedListing();
    const body = await (await call("/api/listings")).json<{ listings: { bike_detail: unknown; reasons: unknown }[]; rejected: unknown[] }>();
    expect(body.listings).toHaveLength(1);
    expect(body.listings[0].bike_detail).toEqual([{ label: "TUM", minutes: 12, km: 4 }]);
    expect(body.listings[0].reasons).toEqual([]);
    expect(body.rejected).toEqual([]);
  });

  it("reports runs with a derived status and the next scheduled run", async () => {
    await seedListing();
    const body = await (await call("/api/runs")).json<{ runs: { status: string; pending: number }[]; nextRunAt: string }>();
    expect(body.runs[0]).toMatchObject({ status: "stalled", pending: 1 }); // queued 2 h ago, no progress
    expect(body.nextRunAt).toBe("2026-10-22T13:00:00.000Z");
  });
});

describe("writes", () => {
  it("fail closed without the API_TOKEN secret", async () => {
    const res = await call("/api/run", post(undefined), { ...env, API_TOKEN: undefined });
    expect(res.status).toBe(503);
  });

  it("reject a wrong or missing token", async () => {
    expect((await call("/api/run", post(undefined, "nope"))).status).toBe(401);
    expect((await call("/api/run", post(undefined, null))).status).toBe(401);
  });

  it("start a manual run, then enforce the cooldown", async () => {
    const q = fakeQueue();
    const res = await call("/api/run", post(undefined), env, q);
    expect(res.status).toBe(202);
    expect(q.sent.map((m) => m.body.kind)).toEqual(["search"]);
    const again = await call("/api/run", post(undefined), env, q);
    expect(again.status).toBe(429);
    expect(again.headers.get("retry-after")).toBe("600");
  });

  it("set triage, validating the value", async () => {
    const id = await seedListing();
    expect((await call(`/api/listings/${id}/triage`, post({ triage: "interested" }))).status).toBe(200);
    expect((await store.getListing(env.DB, id))?.triage).toBe("interested");
    expect((await call(`/api/listings/${id}/triage`, post({ triage: "maybe" }))).status).toBe(400);
    expect((await call(`/api/listings/999999/triage`, post({ triage: "seen" }))).status).toBe(404);
  });
});

describe("runStatus", () => {
  const base: store.RunSummaryRow = {
    id: "r", trigger: "cron", created_at: "2026-10-22T11:55:00Z", pages_total: 2, pages_done: 2,
    pages_failed: 0, errors: null, last_page_at: "2026-10-22T11:56:00Z", scraped: 30, new: 2, matched: 1, pending: 0,
  };
  it("derives the state from page and listing progress", () => {
    expect(runStatus(base, NOW)).toBe("done");
    expect(runStatus({ ...base, pending: 1 }, NOW)).toBe("running");
    expect(runStatus({ ...base, pages_total: null, pages_done: 0, last_page_at: null }, NOW)).toBe("queued");
    expect(runStatus({ ...base, pages_failed: 1 }, NOW)).toBe("failed");
    expect(runStatus({ ...base, pending: 1, last_page_at: "2026-10-22T11:00:00Z" }, NOW)).toBe("stalled");
  });
});

describe("worker entry", () => {
  const worker = (workerExports as unknown as { default: Fetcher }).default;
  it("serves the dashboard and routes /api to the API", async () => {
    const page = await worker.fetch("https://agent.test/");
    expect(page.status).toBe(200);
    expect(await page.text()).toContain("<title>");
    const missing = await worker.fetch("https://agent.test/api/nope");
    expect(missing.status).toBe(404);
  });
});
