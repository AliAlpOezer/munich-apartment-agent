# Status — munich-apartment-agent

Last updated: 2026-10-23 (evening)

## Current focus

Live Cloudflare Worker (`worker/`) aimed at Garching: TUM Campus Garching + SAP Labs Munich
(Garching) as commute anchors, warm rent <= 650 EUR, available by 2027-01-31, <= 37 min by e-bike
(22 km/h, routed) or <= 10 min to a U6 station Garching-Forschungszentrum..Nordfriedhof, dashboard
only (no Telegram). Branch `garching-cloudflare`.

## In flight

- Deployed 2026-10-23: https://apartment-agent.alialp.workers.dev (D1 `apartments` in WEUR, queue
  `apartment-jobs`, cron `0 5-22 * * *`). `API_TOKEN` secret set; the same value is in the user's
  Windows env var `APARTMENT_AGENT_API_TOKEN` (paste into the dashboard's key dialog). No GitHub
  secret: CI doesn't need it.
- Verified on Cloudflare (manual run 08:13 UTC): WG-Gesucht answers Worker egress, Valhalla answered
  all 36 matrix lookups, 36 scraped / 11 matched / 0 errors in ~45 s. Detail jobs used 5-8 ms CPU
  (free limit 10 ms); detail pages are now streamed into HTMLRewriter to widen the margin.
- Cron confirmed: 09:00, 10:00, 11:00 UTC runs all done (08:00 was missed right after deploy).
- 2026-10-23 widening deployed (migration 0002 applied remotely). Its first run had every ride
  estimated (router 100-pair cap); fixed and redeployed. The 12:00 UTC cron re-routed all 116 with
  Valhalla: 37 matched (17 by bike, 20 only via U6, all near Nordfriedhof), 79 rejected.
- 2026-10-23 15:17 UTC: **Kleinanzeigen live** (branch `kleinanzeigen-source`, version `0f0a1a08`,
  migration 0003 applied remotely; D1 bookmark before it:
  `0000001a-00000004-0000510d-f1e4c9e2b2e7c0056fee784b90b37ce6`). First production run: 17 pages,
  0 failed, 240 new Kleinanzeigen listings, 15 matched; WG-Gesucht unchanged at 37 matched. Design:
  `docs/wiki/decisions/kleinanzeigen-source.md`. Swaps stay rejected (user's call, 2026-10-23).
- CPU in production (`wrangler tail --format json`, that run): queue jobs n=153, median 4 ms, p90
  9 ms, max 56 ms; 12 over 10 ms, none failed for CPU. `/api/listings` now median 10 ms, max 19 ms
  (about 350 rows). Watch observability for 1102 errors; the fallback is Workers Paid.

## Blocked

- Nothing.

## Next up

- Merge `kleinanzeigen-source`: production runs it, `main` doesn't yet.
- If `/api/listings` starts hitting CPU limits: build the JSON in SQL (`json_group_array`) instead of
  parsing and re-serializing every row in the Worker.
- Cross-source duplicates (the same flat on both sites shows twice).
- Second pass, porting from the retired Python pipeline: LLM fit ranking (free-first tiers),
  the markdown market wiki, feedback learning from dashboard triage. Then delete the Python package,
  `deploy/` (systemd, HF Space) and `.github/workflows/pages.yml`.

## Recently landed

- 2026-10-23 Kleinanzeigen as a second source: source seam, search streams, page frontier,
  detail-stage routing, swap rule, room-size rule for shared flats; dashboard source badge.

- 2026-10-23 dashboard compound sort: up to three keys (biggest room, cheapest, best EUR/m2,
  shortest ride, newest), default size -> rent -> ride, kept per browser; cards show EUR/m2.

- 2026-10-22 `worker/`: TypeScript Worker (cron + Queues + D1 + static dashboard with map), 49
  tests passing in workerd, live local run: 38 listings scraped, 12 matched.
- 2026-10-22 Python parser moved to selectolax's lexbor backend (selectolax 1.0 dropped the old
  one); legacy suite 93 passed / 1 skipped. The Python scraper still targets the pre-October card
  layout and returns 0 listings live: it is retired, not maintained.
- `b995c23` docs: project knowledge wiki at `docs/wiki/`.
