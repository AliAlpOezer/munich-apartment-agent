// Bike commute per listing: routed minutes from Valhalla's matrix API to every anchor and to the
// nearest transit stop, with a straight-line estimate when the router is unavailable so an outage
// never drops a listing.

import type { Anchor } from "./config";
import type { AnchorTime, BikeTime } from "./types";

// Route/straight-line ratio measured around Garching on 2026-10-22 (1.16-1.36).
export const DETOUR_FACTOR = 1.3;
// The public FOSSGIS instance refuses matrices above 100 source x target pairs (error_code 150,
// observed 2026-10-23), so sources are chunked to fit.
export const MAX_MATRIX_PAIRS = 100;
export const USER_AGENT = "munich-apartment-agent/0.2 (+https://github.com/AliAlpOezer/munich-apartment-agent)";

export type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export interface Point {
  lat: number;
  lng: number;
}

export function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLng = (lng2 - lng1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * 6371.0088 * Math.asin(Math.sqrt(a));
}

function summarize(perAnchor: AnchorTime[], perStop: AnchorTime[], source: BikeTime["source"]): BikeTime {
  const slowest = perAnchor.reduce((a, b) => (b.minutes > a.minutes ? b : a));
  const stop = perStop.length ? perStop.reduce((a, b) => (b.minutes < a.minutes ? b : a)) : null;
  return { minutes: slowest.minutes, km: slowest.km, source, perAnchor, stop };
}

const round1 = (n: number) => Math.round(n * 10) / 10;

function estimateLeg(p: Point, to: Anchor, speedKmh: number): AnchorTime {
  const km = haversineKm(p.lat, p.lng, to.lat, to.lng) * DETOUR_FACTOR;
  return { label: to.label, km: round1(km), minutes: round1((km / speedKmh) * 60) };
}

export function estimateBikeTime(p: Point, anchors: Anchor[], stops: Anchor[], speedKmh: number): BikeTime {
  return summarize(
    anchors.map((a) => estimateLeg(p, a, speedKmh)),
    stops.map((s) => estimateLeg(p, s, speedKmh)),
    "estimate",
  );
}

interface MatrixCell {
  from_index: number;
  to_index: number;
  time: number | null; // seconds
  distance: number | null; // km
}

async function routeChunk(
  points: Point[], anchors: Anchor[], stops: Anchor[], speedKmh: number, routerUrl: string, fetcher: Fetcher,
): Promise<BikeTime[]> {
  const targets = [...anchors, ...stops];
  const body = {
    sources: points.map((p) => ({ lat: p.lat, lon: p.lng })),
    targets: targets.map((a) => ({ lat: a.lat, lon: a.lng })),
    costing: "bicycle",
    costing_options: { bicycle: { bicycle_type: "hybrid", cycling_speed: speedKmh } },
  };
  const res = await fetcher(`${routerUrl}/sources_to_targets`, {
    method: "POST",
    headers: { "content-type": "application/json", "user-agent": USER_AGENT },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15_000),
  });
  if (!res.ok) throw new Error(`router ${res.status}`);
  const data = (await res.json()) as { sources_to_targets?: MatrixCell[][] };
  const rows = data.sources_to_targets;
  if (!Array.isArray(rows) || rows.length !== points.length) throw new Error("router: malformed matrix");

  return points.map((p, i) => {
    const row = rows[i];
    let routed = true;
    const legs = targets.map((t, j) => {
      const cell = row?.find((c) => c.to_index === j);
      if (cell?.time == null || cell.distance == null) {
        // Unroutable pair (e.g. snapped off-network): estimate it. Only anchor legs decide the
        // flag, since a stop leg rarely matters and is often a long detour anyway.
        if (j < anchors.length) routed = false;
        return estimateLeg(p, t, speedKmh);
      }
      return { label: t.label, km: round1(cell.distance), minutes: round1(cell.time / 60) };
    });
    return summarize(legs.slice(0, anchors.length), legs.slice(anchors.length), routed ? "valhalla" : "estimate");
  });
}

/** Bike time for each point (null where the point is unknown). Never throws for router failures. */
export async function bikeTimes(
  points: (Point | null)[], anchors: Anchor[], stops: Anchor[], speedKmh: number, routerUrl: string,
  fetcher: Fetcher,
): Promise<{ times: (BikeTime | null)[]; routerError: string | null }> {
  const times: (BikeTime | null)[] = points.map(() => null);
  const known = points.flatMap((p, i) => (p ? [{ p, i }] : []));
  let routerError: string | null = null;
  const perRequest = Math.max(1, Math.floor(MAX_MATRIX_PAIRS / (anchors.length + stops.length)));
  for (let k = 0; k < known.length; k += perRequest) {
    const chunk = known.slice(k, k + perRequest);
    let result: BikeTime[];
    try {
      result = await routeChunk(chunk.map((c) => c.p), anchors, stops, speedKmh, routerUrl, fetcher);
    } catch (e) {
      routerError = e instanceof Error ? e.message : String(e);
      result = chunk.map((c) => estimateBikeTime(c.p, anchors, stops, speedKmh));
    }
    chunk.forEach((c, n) => (times[c.i] = result[n]));
  }
  return { times, routerError };
}
