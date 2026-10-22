// Regenerates public/isochrone.geojson: the area within MAX_BIKE_MINUTES by bike of each anchor,
// drawn on the dashboard map. Reads the criteria from wrangler.jsonc so the overlay matches the
// filter. Run after changing ANCHORS, BIKE_SPEED_KMH or MAX_BIKE_MINUTES:
//   node scripts/isochrone.mjs
import { readFile, writeFile } from "node:fs/promises";

const root = new URL("../", import.meta.url);
const jsonc = await readFile(new URL("wrangler.jsonc", root), "utf8");
const { vars } = JSON.parse(jsonc.replace(/^\s*\/\/.*$/gm, ""));
const userAgent = "munich-apartment-agent/0.2 (+https://github.com/AliAlpOezer/munich-apartment-agent)";

const features = [];
for (const anchor of vars.ANCHORS) {
  const query = {
    locations: [{ lat: anchor.lat, lon: anchor.lng }],
    costing: "bicycle",
    costing_options: { bicycle: { bicycle_type: "hybrid", cycling_speed: vars.BIKE_SPEED_KMH } },
    contours: [{ time: vars.MAX_BIKE_MINUTES }],
    polygons: true,
    reverse: true, // time to reach the anchor, i.e. the commute direction
    generalize: 200, // metres: smooth the outline for display
    denoise: 1, // keep only the main reachable area, no detached islands
  };
  const res = await fetch(`${vars.ROUTER_URL}/isochrone`, {
    method: "POST",
    headers: { "content-type": "application/json", "user-agent": userAgent },
    body: JSON.stringify(query),
  });
  if (!res.ok) throw new Error(`isochrone for ${anchor.label}: HTTP ${res.status} ${await res.text()}`);
  const geo = await res.json();
  const [feature] = geo.features;
  // Outer ring only: holes (lakes, motorway pockets) add noise to an orientation overlay.
  const polygons = feature.geometry.type === "MultiPolygon" ? feature.geometry.coordinates : [feature.geometry.coordinates];
  const outer = polygons.map((p) => p[0]).sort((a, b) => b.length - a.length)[0];
  const ring = outer.map(([lng, lat]) => [+lng.toFixed(5), +lat.toFixed(5)]);
  features.push({
    type: "Feature",
    properties: { anchor: anchor.label, minutes: vars.MAX_BIKE_MINUTES, speedKmh: vars.BIKE_SPEED_KMH },
    geometry: { type: "Polygon", coordinates: [ring] },
  });
  console.log(`${anchor.label}: ${ring.length} points`);
}

await writeFile(
  new URL("public/isochrone.geojson", root),
  `${JSON.stringify({ type: "FeatureCollection", features })}\n`,
);
