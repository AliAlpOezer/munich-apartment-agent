import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import { handleJob, MAX_FETCH_ATTEMPTS, startRun } from "../src/pipeline";
import * as store from "../src/store";
import type { Job } from "../src/types";
import detailPage from "./fixtures/detail.html?raw";
import emptyPage from "./fixtures/search-empty.html?raw";
import { deps, fakeFetcher, fakeQueue, html, searchPage, valhallaRoute, type Route } from "./helpers";

const WG = "https://www.wg-gesucht.de/";
const ROUTER = "https://valhalla1.openstreetmap.de";
// Fixture order: Freimann, Neufahrn, Oberschleissheim, Dietersheim, Hasenbergl, Bogenhausen.
const MINUTES = [28, 24, 31, 9, 36, 40];
const SEARCH = `${WG}wg-zimmer-und-1-zimmer-wohnungen-und-wohnungen-und-haeuser-in-Muenchen.90.0+1+2+3.1`;
const PAGE0 = `${SEARCH}.0.html`;
const PAGE1 = `${SEARCH}.1.html`;

function routes(overrides: Record<string, Route> = {}) {
  return {
    [`${ROUTER}/`]: valhallaRoute((i) => MINUTES[i]),
    [PAGE0]: () => html(searchPage),
    [PAGE1]: () => html(emptyPage),
    [WG]: () => html(detailPage),
    ...overrides,
  };
}

async function drain(q: ReturnType<typeof fakeQueue>, fetcher: ReturnType<typeof fakeFetcher>, now?: Date) {
  const d = deps(fetcher, q, now);
  for (let i = 0; i < q.sent.length; i++) {
    const outcome = await handleJob(q.sent[i].body, 1, d);
    expect(outcome).toEqual({ ack: true });
  }
}

const rows = async () =>
  (await env.DB.prepare("SELECT * FROM listings ORDER BY external_id").all<store.ListingRow>()).results;

beforeEach(async () => {
  await env.DB.batch([
    env.DB.prepare("DELETE FROM listings"),
    env.DB.prepare("DELETE FROM run_pages"),
    env.DB.prepare("DELETE FROM runs"),
  ]);
});

describe("a full run", () => {
  it("scrapes, filters on bike time, resolves warm rent and matches", async () => {
    const q = fakeQueue();
    const fetcher = fakeFetcher(routes());
    const runId = await startRun(deps(fetcher, q), "cron");
    await drain(q, fetcher);

    const all = await rows();
    expect(all).toHaveLength(6);
    const byId = Object.fromEntries(all.map((r) => [r.external_id, r]));

    // Within 30 min of both anchors -> detail fetched -> matched with the resolved warm rent.
    for (const id of ["7335451", "4061496", "14265492"]) {
      expect(byId[id]).toMatchObject({ stage: "matched", price_warm: 650, price_cold: 600, detail_status: "ok" });
    }
    expect(JSON.parse(byId["14265492"].bike_detail!)).toEqual([
      { label: "TUM", minutes: 9, km: 3 }, { label: "SAP", minutes: 9.5, km: 3 },
    ]);
    // Too far: rejected on the card, no detail fetch.
    expect(byId["3770524"]).toMatchObject({ stage: "rejected", detail_status: null });
    expect(JSON.parse(byId["3770524"].reasons)).toEqual(["bike 32 min > 30 min"]);
    expect(JSON.parse(byId["13293325"].reasons)).toEqual(["bike 41 min > 30 min"]);

    const detailFetches = fetcher.calls.filter((u) => /\.\d+\.html$/.test(u));
    expect(detailFetches).toHaveLength(3);

    const [summary] = await store.runSummaries(env.DB, 1);
    expect(summary).toMatchObject({
      id: runId, pages_total: 2, pages_done: 2, pages_failed: 0, scraped: 6, new: 6, matched: 3, pending: 0,
    });
  });

  it("is idempotent under redelivery and only treats unseen listings as new", async () => {
    const q = fakeQueue();
    const fetcher = fakeFetcher(routes());
    await startRun(deps(fetcher, q), "cron");
    await drain(q, fetcher);
    // Redeliver every message of the run.
    const replay = fakeQueue();
    replay.sent.push(...q.sent);
    await drain(replay, fetcher);
    expect(await rows()).toHaveLength(6);

    await env.DB.prepare("UPDATE listings SET triage = 'interested' WHERE external_id = '14265492'").run();
    const q2 = fakeQueue();
    const second = await startRun(deps(fetcher, q2, new Date("2026-10-22T13:00:00Z")), "cron");
    await drain(q2, fetcher, new Date("2026-10-22T13:00:00Z"));

    const after = await rows();
    expect(after).toHaveLength(6);
    expect(after.every((r) => r.last_seen_run === second)).toBe(true);
    expect(after.find((r) => r.external_id === "14265492")?.triage).toBe("interested"); // user's fact untouched
    expect(q2.sent.filter((m) => m.body.kind === "detail")).toHaveLength(0);
    const [summary] = await store.runSummaries(env.DB, 1);
    expect(summary).toMatchObject({ id: second, scraped: 6, new: 0, matched: 0 });
  });

  it("spaces queued fetches instead of bursting them", async () => {
    const q = fakeQueue();
    const fetcher = fakeFetcher(routes());
    await startRun(deps(fetcher, q), "cron");
    await drain(q, fetcher);
    const details = q.sent.filter((m) => m.body.kind === "detail").map((m) => m.delaySeconds);
    expect(details).toEqual([0, 3, 6]);
  });
});

describe("failure handling", () => {
  it("records a 200 page without parseable cards as a failed page", async () => {
    const q = fakeQueue();
    const broken = searchPage.replaceAll("wgg-list-card", "wgg-tile");
    const fetcher = fakeFetcher(routes({
      [PAGE0]: () => html(broken),
    }));
    await startRun(deps(fetcher, q), "manual");
    await drain(q, fetcher);
    const [summary] = await store.runSummaries(env.DB, 1);
    expect(summary.pages_failed).toBe(1);
    expect(summary.errors).toMatch(/page 0: 0 cards parsed \(6 map markers\)/);
  });

  it("retries a failing search page with backoff, then records the failure", async () => {
    const q = fakeQueue();
    const fetcher = fakeFetcher(routes({
      [PAGE0]: () => html("upstream down", 503),
    }));
    const d = deps(fetcher, q);
    await startRun(d, "cron");
    const job = q.sent[0].body;
    expect(await handleJob(job, 1, d)).toEqual({ ack: false, retryAfterSeconds: 60 });
    expect(await handleJob(job, 2, d)).toEqual({ ack: false, retryAfterSeconds: 300 });
    expect(await handleJob(job, MAX_FETCH_ATTEMPTS, d)).toEqual({ ack: true });
    const [summary] = await store.runSummaries(env.DB, 1);
    expect(summary.errors).toMatch(/fetch failed: HTTP 503/);
  });

  it("decides on card facts when the detail page keeps failing", async () => {
    const q = fakeQueue();
    const fetcher = fakeFetcher(routes({ [`${WG}wg-zimmer-in-`]: () => html("err", 500) }));
    const d = deps(fetcher, q);
    await startRun(d, "cron");
    await handleJob(q.sent[0].body, 1, d);
    const detail = q.sent.find((m) => m.body.kind === "detail")!.body as Extract<Job, { kind: "detail" }>;
    expect((await handleJob(detail, 1, d)).ack).toBe(false);
    expect(await handleJob(detail, MAX_FETCH_ATTEMPTS, d)).toEqual({ ack: true });
    const row = await store.getListing(env.DB, detail.listingId);
    expect(row).toMatchObject({ stage: "matched", detail_status: "failed", price_warm: null });
  });

  it("rejects a listing whose detail page is gone", async () => {
    const q = fakeQueue();
    const fetcher = fakeFetcher(routes({ [`${WG}wg-zimmer-in-`]: () => html("weg", 404) }));
    const d = deps(fetcher, q);
    await startRun(d, "cron");
    await handleJob(q.sent[0].body, 1, d);
    const detail = q.sent.find((m) => m.body.kind === "detail")!.body as Extract<Job, { kind: "detail" }>;
    expect(await handleJob(detail, 1, d)).toEqual({ ack: true });
    const row = await store.getListing(env.DB, detail.listingId);
    expect(row?.stage).toBe("rejected");
    expect(JSON.parse(row!.reasons)).toEqual(["listing no longer online"]);
  });

  it("keeps listings with estimated bike times when the router is down", async () => {
    const q = fakeQueue();
    const fetcher = fakeFetcher(routes({ [`${ROUTER}/`]: () => new Response("no", { status: 502 }) }));
    await startRun(deps(fetcher, q), "cron");
    await drain(q, fetcher);
    const all = await rows();
    expect(all.every((r) => r.bike_source === "estimate")).toBe(true);
    // Dietersheim is ~3 km from TUM: well inside 30 min even as an estimate.
    expect(all.find((r) => r.external_id === "14265492")?.stage).toBe("matched");
  });

  it("refuses URLs outside the source host", async () => {
    const q = fakeQueue();
    const fetcher = fakeFetcher({});
    const d = deps(fetcher, q);
    await store.createRun(env.DB, "r1", "manual", {}, "2026-10-22T12:00:00Z");
    expect(await handleJob({ kind: "search", runId: "r1", page: 1, url: "https://evil.test/x" }, 1, d)).toEqual({ ack: true });
    expect(fetcher.calls).toEqual([]);
  });

  it("re-enqueues detail jobs that were lost for over an hour", async () => {
    const q = fakeQueue();
    const fetcher = fakeFetcher(routes());
    await startRun(deps(fetcher, q), "cron");
    await handleJob(q.sent[0].body, 1, deps(fetcher, q)); // page 0 only; details never processed
    const later = fakeQueue();
    await startRun(deps(fetcher, later, new Date("2026-10-22T14:00:00Z")), "cron");
    expect(later.sent.filter((m) => m.body.kind === "detail")).toHaveLength(3);
  });
});
