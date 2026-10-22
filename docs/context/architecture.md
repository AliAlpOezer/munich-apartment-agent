# Architecture — munich-apartment-agent

## Shape

One Cloudflare Worker (`worker/`, TypeScript, free plan) does everything. A cron trigger (hourly,
05-22 UTC) or the dashboard's "Search now" creates a run row in D1 and enqueues a `search` job on
the `apartment-jobs` queue. The queue consumer runs at concurrency 1, so every outbound request is
serialized. A search-page job fetches one WG-Gesucht results page, parses the cards plus the map
`markers` JSON (exact lat/lng per listing), routes new listings' e-bike minutes to every anchor
through Valhalla's matrix API (haversine x 1.3 estimate on failure), filters on card facts, and
upserts rows. Rows that pass are enqueued as `detail` jobs. A detail job fetches the listing page,
resolves warm/cold rent, re-runs the same filter and makes the single stage transition
`pending_detail -> matched|rejected`. Static assets (`worker/public/`) are the dashboard; `/api/*`
runs the Worker first.

## Map

| Path | Holds |
|---|---|
| `worker/src/index.ts` | `fetch` (API vs assets), `scheduled`, `queue` handlers; builds `Deps` |
| `worker/src/pipeline.ts` | `startRun`, `handleJob` (search page, detail), retry/backoff, politeness spacing |
| `worker/src/wggesucht.ts` | search URL + derived radius, card/marker/pagination parsing, detail cost parsing |
| `worker/src/bike.ts` | Valhalla `sources_to_targets` client, estimate fallback, haversine |
| `worker/src/filter.ts` | pure match rules (rent, size, available-by, minimum stay, bike minutes) |
| `worker/src/store.ts` + `worker/migrations/` | every SQL statement; D1 schema (`runs`, `run_pages`, `listings`) |
| `worker/src/api.ts` | `/api/config`, `/api/listings`, `/api/runs`, `POST /api/run`, `POST /api/listings/:id/triage` |
| `worker/src/config.ts` | typed, validated criteria from `wrangler.jsonc` vars; cron mirror `SCHEDULE` |
| `worker/public/` | vanilla-JS dashboard (Leaflet map, OSM tiles), `isochrone.geojson` overlay |
| `worker/scripts/isochrone.mjs` | regenerates the overlay from the vars |
| `worker/test/` | vitest in workerd; anonymized live fixtures captured 2026-10-22 |
| `src/apartment_agent/`, `deploy/` | retired Python/LangGraph pipeline (box era); kept until the LLM/wiki/feedback port |

## Boundaries

- Filtering is pure code over stored columns; no model in control flow. Verdict reasons are stored.
- One writer per fact: the pipeline owns listing facts and `stage`; only the API writes `triage`.
- Idempotency is structural: `UNIQUE(source, external_id)`, upserts, guarded stage `UPDATE`, run
  counts derived from rows. Redelivered or overlapping jobs are harmless.
- A 200 page with no parseable cards (while markers exist) is a failed page, never "0 new".
- Writes need the `API_TOKEN` secret and fail closed without it; reads are open (use Cloudflare
  Access for privacy).
- Search radius is derived (speed x minutes + anchor spread), a guaranteed superset of the
  routed area; the routed minutes decide.

## External dependencies

- **WG-Gesucht** — plain `fetch` with browser headers (no TLS impersonation needed as of 2026-10-22).
- **Valhalla (FOSSGIS public instance)** — bike routing matrix, no key; one call per search page.
- **Cloudflare** — Workers (cron, queue consumer, static assets), Queues, D1.
- **OpenStreetMap tiles + Leaflet 1.9.4 (cdnjs, SRI)** — dashboard map. CARTO basemaps now
  require an API key, so they are not used.
