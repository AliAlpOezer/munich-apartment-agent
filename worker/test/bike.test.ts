import { describe, expect, it } from "vitest";
import { bikeTimes, DETOUR_FACTOR, estimateBikeTime, haversineKm } from "../src/bike";
import type { Anchor } from "../src/config";
import { fakeFetcher, valhallaRoute } from "./helpers";

const anchors: Anchor[] = [
  { label: "TUM", name: "TUM", lat: 48.2625535, lng: 11.6680432 },
  { label: "SAP", name: "SAP", lat: 48.2641004, lng: 11.6607557 },
];
const ROUTER = "https://router.test";
const dietersheim = { lat: 48.282421, lng: 11.672301 };

describe("haversineKm", () => {
  it("measures TUM to SAP Garching at about 0.56 km", () => {
    expect(haversineKm(anchors[0].lat, anchors[0].lng, anchors[1].lat, anchors[1].lng)).toBeCloseTo(0.56, 1);
  });
});

describe("bikeTimes", () => {
  it("uses routed times and reports the slower anchor", async () => {
    const fetcher = fakeFetcher({ [ROUTER]: valhallaRoute((i) => [12, 25][i]) });
    const { times, routerError } = await bikeTimes([dietersheim, null, dietersheim], anchors, 22, ROUTER, fetcher);
    expect(routerError).toBeNull();
    expect(fetcher.calls).toEqual([`${ROUTER}/sources_to_targets`]); // one batched request
    expect(times[0]).toEqual({
      minutes: 12.5, km: 4, source: "valhalla",
      perAnchor: [{ label: "TUM", minutes: 12, km: 4 }, { label: "SAP", minutes: 12.5, km: 4 }],
    });
    expect(times[1]).toBeNull(); // no coordinates: unknown, never guessed
    expect(times[2]?.minutes).toBe(25.5);
  });

  it("sends the configured speed with the bicycle costing", async () => {
    let sent: { costing: string; costing_options: { bicycle: { cycling_speed: number } } } | null = null;
    const fetcher = fakeFetcher({
      [ROUTER]: (url, init) => {
        sent = JSON.parse(String(init?.body));
        return valhallaRoute(() => 10)(url, init);
      },
    });
    await bikeTimes([dietersheim], anchors, 22, ROUTER, fetcher);
    expect(sent!.costing).toBe("bicycle");
    expect(sent!.costing_options.bicycle.cycling_speed).toBe(22);
  });

  it("falls back to a flagged estimate when the router fails", async () => {
    const fetcher = fakeFetcher({ [ROUTER]: () => new Response("busy", { status: 429 }) });
    const { times, routerError } = await bikeTimes([dietersheim], anchors, 22, ROUTER, fetcher);
    expect(routerError).toBe("router 429");
    expect(times[0]).toEqual(estimateBikeTime(dietersheim, anchors, 22));
    expect(times[0]?.source).toBe("estimate");
  });

  it("estimates only the pair the router could not route", async () => {
    const fetcher = fakeFetcher({
      [ROUTER]: () => Response.json({
        sources_to_targets: [[
          { from_index: 0, to_index: 0, time: 600, distance: 3.2 },
          { from_index: 0, to_index: 1, time: null, distance: null },
        ]],
      }),
    });
    const { times } = await bikeTimes([dietersheim], anchors, 22, ROUTER, fetcher);
    expect(times[0]?.source).toBe("estimate");
    expect(times[0]?.perAnchor[0]).toEqual({ label: "TUM", minutes: 10, km: 3.2 });
  });
});

describe("estimateBikeTime", () => {
  it("applies the detour factor at the given speed", () => {
    const est = estimateBikeTime(dietersheim, anchors.slice(0, 1), 22);
    const km = haversineKm(dietersheim.lat, dietersheim.lng, anchors[0].lat, anchors[0].lng) * DETOUR_FACTOR;
    expect(est.km).toBeCloseTo(km, 1);
    expect(est.minutes).toBeCloseTo((km / 22) * 60, 1);
  });
});
