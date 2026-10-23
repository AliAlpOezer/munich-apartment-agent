# Architecture — munich-apartment-agent

## Shape

One Cloudflare Worker (`worker/`, TypeScript, free plan) does everything. A cron trigger (hourly,
05-22 UTC) or the dashboard's "Search now" creates a run row in D1 and enqueues page 0 of every
**search stream** (WG-Gesucht; Kleinanzeigen flats, WG/temporary, houses) on the `apartment-jobs`
queue. The queue consumer runs at concurrency 1, so every outbound request is serialized. A
search-page job asks the stream's **source adapter** to parse the page, claims linked pages it has
not seen (`run_pages` rows, status `queued`), routes e-bike minutes for listings with a position to
every anchor and the nearest U6 station through Valhalla's matrix API (chunked to <= 100 pairs;
haversine x 1.3 estimate on failure), filters on card facts, and upserts rows. Known listings
decided under older criteria (or with estimated rides) are re-decided, taking facts the card lacks
(Kleinanzeigen: position, availability) from the stored row. Rows that pass become `detail` jobs. A
detail job resolves warm/cold rent, and for Kleinanzeigen the position (then routes it), re-runs the
same filter and makes the single transition `pending_detail -> matched|rejected`. Static assets
(`worker/public/`) are the dashboard; `/api/*` runs the Worker first.

## Map

| Path | Holds |
|---|---|
| `worker/src/index.ts` | `fetch` (API vs assets), `scheduled`, `queue` handlers; builds `Deps` |
| `worker/src/pipeline.ts` | `startRun`, `handleJob` (search page, detail), page frontier, retry/backoff, spacing |
| `worker/src/sources.ts`, `registry.ts` | `Source` contract (streams, parsers, `detailOnly`), derived search area, registry |
| `worker/src/wggesucht.ts` | WG-Gesucht: search URL, card/marker/pagination parsing, detail costs (HTMLRewriter) |
| `worker/src/kleinanzeigen.ts` | Kleinanzeigen: 3 category streams, card string scan, detail facts incl. og: position |
| `worker/src/bike.ts` | Valhalla `sources_to_targets` client, estimate fallback, haversine |
| `worker/src/filter.ts` | pure match rules (rent, size, available-by, minimum stay, swap, bike minutes) |
| `worker/src/store.ts` + `worker/migrations/` | every SQL statement; D1 schema (`runs`, `run_pages` per stream, `listings`) |
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
- Search radius is derived (bike reach around the anchors and around the U6 stops), a guaranteed
  superset of the routed area; the routed minutes decide.
- Criteria are versioned per decision (vars plus `RULES_REVISION` in `pipeline.ts`); changing either
  re-decides listings that are still online on the next run.
- Adapters only produce facts; nothing source-specific reaches `filter.ts`. A page is enqueued once
  per run: claimed under `PRIMARY KEY (run_id, stream, page)` before its job is sent. A run is done
  when no page is `queued` and no listing is pending.

## External dependencies

- **WG-Gesucht** — plain `fetch` with browser headers (no TLS impersonation needed as of 2026-10-22).
- **Kleinanzeigen** — same headers; Akamai Bot Manager in front but Cloudflare egress passed
  (2026-10-23). Gesuche are skipped per card (the offers-only facet is disallowed by robots.txt).
  `SOURCES` in `wrangler.jsonc` switches it off.
- **Valhalla (FOSSGIS public instance)** — bike routing matrix, no key; max 100 source x target
  pairs per request, so 9 listings per call with 11 targets.
- **Cloudflare** — Workers (cron, queue consumer, static assets), Queues, D1.
- **OpenStreetMap tiles + Leaflet 1.9.4 (cdnjs, SRI)** — dashboard map. CARTO basemaps now
  require an API key, so they are not used.
