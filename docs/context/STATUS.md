# Status — munich-apartment-agent

Last updated: 2026-10-23 (afternoon)

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
- Open: search-page CPU not measured yet (detail jobs 5-8 ms of the free 10 ms). If search pages
  approach 10 ms, cut the HTML before parsing or move to Workers Paid.

## Blocked

- Nothing.

## Next up

- Second pass, porting from the retired Python pipeline: LLM fit ranking (free-first tiers),
  the markdown market wiki, feedback learning from dashboard triage. Then delete the Python package,
  `deploy/` (systemd, HF Space) and `.github/workflows/pages.yml`.

## Recently landed

- 2026-10-23 dashboard compound sort: up to three keys (biggest room, cheapest, best EUR/m2,
  shortest ride, newest), default size -> rent -> ride, kept per browser; cards show EUR/m2.

- 2026-10-22 `worker/`: TypeScript Worker (cron + Queues + D1 + static dashboard with map), 49
  tests passing in workerd, live local run: 38 listings scraped, 12 matched.
- 2026-10-22 Python parser moved to selectolax's lexbor backend (selectolax 1.0 dropped the old
  one); legacy suite 93 passed / 1 skipped. The Python scraper still targets the pre-October card
  layout and returns 0 listings live: it is retired, not maintained.
- `b995c23` docs: project knowledge wiki at `docs/wiki/`.
