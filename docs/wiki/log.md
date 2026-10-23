# Wiki log

Append-only history of documentation passes. Newest first.

## 2026-10-23 — 37-minute limit, U6 alternative, retroactive criteria

**Pages updated**: `decisions/bike-time-filter` (update section, Schleissheim alternatives),
`decisions/cloudflare-workers-hosting` (invariant 2 now allows version-guarded re-decisions).

**Evidence sources** (checked 2026-10-23)
- Valhalla matrix at 22 km/h from both anchors to 8 points in Ober-/Unterschleissheim (30.5-36.9 min).
- Overpass station nodes for the 9 U6 stations Garching-Forschungszentrum to Nordfriedhof.
- WG-Gesucht: 118 results at a 14.9 km radius, 6 pages.
- Reproduced the router failure: 10 x 11 and 20 x 11 matrices -> HTTP 400 error_code 150
  "Exceeded max locations: 100"; 5 x 11 -> 200.
- Deployed run 11:55 UTC: 116 scraped, 45 matched (25 via the U6), all rides estimated (the bug).

## 2026-10-22 — Cloudflare Worker revival (Garching)

Design record written before the code, for the move from the Python box to one Cloudflare Worker
and from the Alte Heide radius to routed e-bike minutes around TUM and SAP Garching.

**Pages created**: `decisions/cloudflare-workers-hosting`, `decisions/bike-time-filter`.
**Pages updated**: `index` (intro, two new decisions, superseded marks); superseded banners on
`decisions/radius-search`, `decisions/tls-impersonation-scraping`, `decisions/local-sqlite-vs-supabase`.

**Evidence sources** (all checked 2026-10-22)
- Live WG-Gesucht pages: plain HTTPS GET returns 200 (server Apache, no bot wall); cards are
  `a.wgg-list-card[data-id]`; the map config embeds `markers` with lat/lng; an 11 km radius search
  at <= 650 EUR returned 2 pages / 34-38 listings.
- Valhalla public instance (valhalla1.openstreetmap.de) matrix and isochrone calls without a key;
  its terms page was behind a bot wall (unverified terms, hence one batched call per page).
- Nominatim geocodes for TUM CIT (Boltzmannstr. 3) and SAP Labs Munich (F.-L.-Bauer-Str. 5).
- Cloudflare limits page: free plan 10 ms CPU per invocation (HTTP and cron), 50 subrequests,
  5 cron triggers; Queues on the free plan with 10,000 operations/day.
- `worker/` test suite: 49 passed. Local `wrangler dev` run against the live site: 38 scraped,
  12 matched, 26 rejected with reasons.

## 2026-07-12 — initial knowledge-wiki bundle

First pass. Created the full bundle: 1 index, this log, 1 state page, 13 decision pages, 9 component pages, 4 concept pages.

**Pages created**
- state: `current-state.md`
- decisions: `deterministic-core-llm-at-edges`, `free-first-tiered-routing`, `warmmiete-detail-fetch`, `structured-output-fallback`, `local-sqlite-vs-supabase`, `tls-impersonation-scraping`, `resilience-and-safety`, `human-in-the-loop-feedback`, `llm-wiki-knowledge-layer`, `radius-search`, `web-dashboard-architecture`, `wide-eval-bands`, `per-run-heartbeat`
- components: `orchestration`, `scraper`, `filter`, `llm-router`, `database`, `notifications-and-feedback`, `wiki-layer`, `web-dashboard`, `evals`
- concepts: `langgraph-state-machine`, `warmmiete-vs-kaltmiete`, `llm-tiering-and-structured-output`, `settings-and-env-precedence`

**Evidence sources**
- The session codebase digest (2026-07-12) for pipeline shape, component internals, and design rationale.
- `git log` — verified commit count **30** (`git log --oneline | wc -l`); confirmed HEAD is `2327809` and `git log origin/main..HEAD` shows **0** ahead (the digest's "one ahead, unpushed" note is now resolved — the fix is pushed).
- Test run — **93 passed, 1 skipped** (the 1 skip is the `RUN_LIVE_EVALS`-gated live eval).
- Spot-checked files for citations: `graph.py:293` (`route_after_dedup`), `graph.py:298-323` (`_timed` + wiring), `models.py:54-66` (`effective_warm_rent`), `notify/telegram.py:62-70` (`format_heartbeat`), `main.py:61/98/197` (`_run_graph` + heartbeat), `nodes/filter.py:30` (`passes_filter`), `pyproject.toml` (dependencies), package layout under `src/apartment_agent/`.
- Live-session diagnostics: deployment on "alpiclawd" (systemd timer + dashboard units), the Tailscale MTU black hole (≤~1028 B pass / ≥~1228 B drop), the broken HTTPS dashboard URL (proxy → dead port 18789 vs app on 8000), and the constant scraped=18/matched=12/new=0 anomaly over 18+ hours.
