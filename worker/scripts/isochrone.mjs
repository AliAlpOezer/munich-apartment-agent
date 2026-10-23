// Regenerates public/isochrone.geojson for the dashboard map: the area within MAX_BIKE_MINUTES by
// bike of each anchor, and within MAX_BIKE_TO_STOP_MINUTES of each transit stop. Reads the criteria
// from wrangler.jsonc so the overlay matches the filter. Run after changing ANCHORS, TRANSIT_STOPS,
// BIKE_SPEED_KMH or either minutes limit:
//   node scripts/isochrone.mjs
import { readFile, writeFile } from "node:fs/promises";

const root = new URL("../", import.meta.url);
const jsonc = await readFile(new URL("wrangler.jsonc", root), "utf8");
const { vars } = JSON.parse(jsonc.replace(/^\s*\/\/.*$/gm, ""));
const userAgent = "munich-apartment-agent/0.2 (+https://github.com/AliAlpOezer/munich-apartment-agent)";

async function reach(place, minutes, kind) {
  const query = {
    locations: [{ lat: place.lat, lon: place.lng }],
    costing: "bicycle",
    costing_options: { bicycle: { bicycle_type: "hybrid", cycling_speed: vars.BIKE_SPEED_KMH } },
    contours: [{ time: minutes }],
    polygons: true,
    reverse: true, // time to reach the place, i.e. the commute direction
    generalize: kind === "stop" ? 60 : 200, // metres: smooth the outline for display
    denoise: 1, // keep only the main reachable area, no detached islands
  };
  const res = await fetch(`${vars.ROUTER_URL}/isochrone`, {
    method: "POST",
    headers: { "content-type": "application/json", "user-agent": userAgent },
    body: JSON.stringify(query),
  });
  if (!res.ok) throw new Error(`isochrone for ${place.label}: HTTP ${res.status} ${await res.text()}`);
  const [feature] = (await res.json()).features;
  // Outer ring only: holes (lakes, motorway pockets) add noise to an orientation overlay.
  const polygons = feature.geometry.type === "MultiPolygon" ? feature.geometry.coordinates : [feature.geometry.coordinates];
  const outer = polygons.map((p) => p[0]).sort((a, b) => b.length - a.length)[0];
  const ring = outer.map(([lng, lat]) => [+lng.toFixed(5), +lat.toFixed(5)]);
  console.log(`${kind} ${place.label}: ${ring.length} points`);
  return {
    type: "Feature",
    properties: { kind, anchor: place.label, minutes, speedKmh: vars.BIKE_SPEED_KMH },
    geometry: { type: "Polygon", coordinates: [ring] },
  };
}

const features = [];
for (const anchor of vars.ANCHORS) features.push(await reach(anchor, vars.MAX_BIKE_MINUTES, "anchor"));
for (const stop of vars.TRANSIT_STOPS ?? []) features.push(await reach(stop, vars.MAX_BIKE_TO_STOP_MINUTES, "stop"));

await writeFile(
  new URL("public/isochrone.geojson", root),
  `${JSON.stringify({ type: "FeatureCollection", features })}\n`,
);
