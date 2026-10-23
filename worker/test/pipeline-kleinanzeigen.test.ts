import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import { runStatus } from "../src/api";
import { kleinanzeigen, searchRadiusKm } from "../src/kleinanzeigen";
import { handleJob, startRun } from "../src/pipeline";
import * as store from "../src/store";
import detailFlat from "./fixtures/ka-detail-flat.html?raw";
import detailShort from "./fixtures/ka-detail-short.html?raw";
import emptyPage from "./fixtures/ka-search-empty.html?raw";
import searchFixture from "./fixtures/ka-search.html?raw";
import { deps, fakeFetcher, fakeQueue, html, settings, type Route } from "./helpers";

const KA = "https://www.kleinanzeigen.de";
const ROUTER = "https://valhalla1.openstreetmap.de";
const R = searchRadiusKm(settings.criteria);
const search = (path: string, cat: number, page = 1) =>
  `${KA}/${path}/garching-b-muenchen/preis::650/${page > 1 ? `seite:${page}/` : ""}c${cat}l6303r${R}`;
// The fixture was captured at radius 15; its links follow whatever radius was asked for (the
// radius grows with the commute limits).
const wgPage = (url: string) => html(searchFixture.replaceAll("l6303r15", `l6303r${/l6303r(\d+)/.exec(url)![1]}`));

// Detail fixtures by listing: Neufahrn (north of the campus) or Feldmoching (west Munich). The
// Oberschleissheim card says "55 m² · 3 Zi." (the flat), so its stand-in page names a 14 m² room.
const DETAILS: Record<string, string> = {
  "3496292417": detailShort, "3545322242": detailShort,
  "3546382872": detailFlat.replace(/(Wohnfläche<span[^>]*>\s*)9 m²/, (_, label) => `${label}14 m²`),
};
// Router minutes by position: Neufahrn is close; Feldmoching is far by bike and from the U6.
const ride = (lat: number) => (lat > 48.3 ? { bike: 16, stop: 9 } : { bike: 41, stop: 14 });
const router: Route = async (_url, init) => {
  const body = JSON.parse(String(init?.body));
  const rows = body.sources.map((s: { lat: number }, i: number) =>
    body.targets.map((_t: unknown, j: number) => {
      const m = j < settings.criteria.anchors.length ? ride(s.lat).bike : ride(s.lat).stop + (j - 2);
      return { from_index: i, to_index: j, time: m * 60, distance: m / 3 };
    }),
  );
  return Response.json({ sources_to_targets: rows });
};

function routes(overrides: Record<string, Route> = {}): Record<string, Route> {
  return {
    [`${ROUTER}/`]: router,
    [`${KA}/s-`]: () => html(emptyPage), // other categories and further pages: no results
    [`${KA}/s-auf-zeit-wg/`]: (url) => (/\/preis::650\/c199l6303r\d+$/.test(url) ? wgPage(url) : html(emptyPage)),
    [`${KA}/s-anzeige/`]: (url) => html(DETAILS[/\/(\d+)-\d+-\d+$/.exec(url)![1]] ?? "<html>gone</html>"),
    ...overrides,
  };
}

const kaDeps = (fetcher: ReturnType<typeof fakeFetcher>, q: ReturnType<typeof fakeQueue>, now?: Date,
  criteria: Parameters<typeof deps>[3] = {}) => deps(fetcher, q, now, criteria, [kleinanzeigen]);

async function drain(q: ReturnType<typeof fakeQueue>, d: ReturnType<typeof kaDeps>) {
  for (let i = 0; i < q.sent.length; i++) expect(await handleJob(q.sent[i].body, 1, d)).toEqual({ ack: true });
}

const rows = async () =>
  (await env.DB.prepare("SELECT * FROM listings ORDER BY external_id").all<store.ListingRow>()).results;
const byId = async () => Object.fromEntries((await rows()).map((r) => [r.external_id, r]));
const detailFetches = (f: ReturnType<typeof fakeFetcher>) => f.calls.filter((u) => u.includes("/s-anzeige/"));

beforeEach(async () => {
  await env.DB.batch([
    env.DB.prepare("DELETE FROM listings"),
    env.DB.prepare("DELETE FROM run_pages"),
    env.DB.prepare("DELETE FROM runs"),
  ]);
});

describe("a Kleinanzeigen run", () => {
  it("routes positions from detail pages before deciding, and walks every linked page once", async () => {
    const q = fakeQueue();
    const fetcher = fakeFetcher(routes());
    const d = kaDeps(fetcher, q);
    const runId = await startRun(d, "cron");
    await drain(q, d);

    const all = await byId();
    expect(Object.keys(all)).toEqual(["3335842751", "3496292417", "3536207850", "3545322242", "3546382872", "3546651796"]);
    // Near the campus: matched once the detail page gave a position, which was then routed.
    expect(all["3496292417"]).toMatchObject({
      source: "kleinanzeigen", stage: "matched", detail_status: "ok", lat: 48.31133139621653, lng: 11.663525303845162,
      bike_minutes: 16, bike_source: "valhalla", stop_minutes: 9, available_from: "2026-11-01", size_sqm: 20,
      price_listed: 480, price_warm: null,
    });
    // Rent unknown (a short stay priced per night) keeps it, as any unknown does.
    expect(all["3545322242"]).toMatchObject({ stage: "matched", price_listed: null });
    // Its detail page puts it in Feldmoching: too far either way. In "Auf Zeit & WG" the listed
    // price is no cold rent, so only the Warmmiete attribute counts.
    expect(all["3546382872"]).toMatchObject({ stage: "rejected", price_cold: null, price_warm: 620, bike_minutes: 41 });
    expect(JSON.parse(all["3546382872"].reasons)).toEqual(["bike 41 min > 37 min; 14 min to the U6 > 10 min"]);
    // Rejected on the card: no detail page fetched.
    expect(all["3335842751"]).toMatchObject({ stage: "rejected", swap: 1, detail_status: null, lat: null });
    expect(JSON.parse(all["3335842751"].reasons)).toEqual(["flat swap (Tausch) only"]);
    expect(JSON.parse(all["3546651796"].reasons)).toEqual(["size 1 m² < 10 m²"]);
    expect(JSON.parse(all["3536207850"].reasons)).toEqual(["size 9 m² < 10 m²"]);
    expect(detailFetches(fetcher)).toHaveLength(3);

    // Page 0 of three categories, plus pages 2-4 of the WG search; nothing from the other search's link.
    const searches = fetcher.calls.filter((u) => u.includes("/s-") && !u.includes("/s-anzeige/"));
    expect(searches.sort()).toEqual([
      search("s-auf-zeit-wg", 199), search("s-auf-zeit-wg", 199, 2), search("s-auf-zeit-wg", 199, 3),
      search("s-auf-zeit-wg", 199, 4), search("s-haus-mieten", 205), search("s-wohnung-mieten", 203),
    ].sort());
    const [summary] = await store.runSummaries(env.DB, 1);
    expect(summary).toMatchObject({
      id: runId, pages_total: 6, pages_done: 6, pages_failed: 0, scraped: 6, new: 6, matched: 2, pending: 0,
    });
    expect(runStatus(summary, new Date("2026-10-22T12:05:00Z"))).toBe("done");
  });

  it("enqueues each page once, however often it is linked or delivered", async () => {
    const q = fakeQueue();
    const fetcher = fakeFetcher(routes({
      // Every page links pages 2-4, as a sliding window does.
      [`${KA}/s-auf-zeit-wg/`]: wgPage,
    }));
    const d = kaDeps(fetcher, q);
    await startRun(d, "cron");
    await drain(q, d);
    const replay = fakeQueue();
    replay.sent.push(...q.sent.filter((m) => m.body.kind === "search"));
    await drain(replay, d);

    const wgPages = q.sent.filter((m) => m.body.kind === "search" && m.body.stream === "kleinanzeigen:wg");
    expect(wgPages.map((m) => (m.body as { page: number }).page)).toEqual([0, 1, 2, 3]);
    expect(replay.sent.length).toBe(q.sent.filter((m) => m.body.kind === "search").length);
  });

  it("re-decides from the card with the stored position and dates, without fetching details again", async () => {
    const q = fakeQueue();
    const fetcher = fakeFetcher(routes());
    await startRun(kaDeps(fetcher, q), "cron");
    await drain(q, kaDeps(fetcher, q));
    const fetched = detailFetches(fetcher).length;

    const later = new Date("2026-10-22T13:00:00Z");
    const q2 = fakeQueue();
    const d2 = kaDeps(fetcher, q2, later, { maxBikeMinutes: 45 });
    await startRun(d2, "cron");
    await drain(q2, d2);

    const all = await byId();
    // Feldmoching now fits (41 min): matched from stored rent and a ride routed from the stored position.
    expect(all["3546382872"]).toMatchObject({
      stage: "matched", lat: 48.217851359304106, bike_minutes: 41, available_from: "2026-11-01", price_warm: 620,
    });
    expect(all["3335842751"].stage).toBe("rejected"); // still a swap
    expect(detailFetches(fetcher).length).toBe(fetched);
  });

  it("re-routes a detail-stage estimate from the stored position once the router is back", async () => {
    const q = fakeQueue();
    const down = fakeFetcher(routes({ [`${ROUTER}/`]: () => new Response("no", { status: 502 }) }));
    await startRun(kaDeps(down, q), "cron");
    await drain(q, kaDeps(down, q));
    expect((await byId())["3496292417"]).toMatchObject({ stage: "matched", bike_source: "estimate" });

    const later = new Date("2026-10-22T13:00:00Z");
    const q2 = fakeQueue();
    const up = fakeFetcher(routes());
    await startRun(kaDeps(up, q2, later), "cron");
    await drain(q2, kaDeps(up, q2, later));
    expect((await byId())["3496292417"]).toMatchObject({
      stage: "matched", bike_source: "valhalla", bike_minutes: 16, lat: 48.31133139621653,
    });
    expect(detailFetches(up)).toHaveLength(0);
  });
});
