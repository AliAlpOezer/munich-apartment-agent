# Status — munich-apartment-agent

Last updated: 2026-10-23

## Current focus

Revived as a Cloudflare Worker (`worker/`) aimed at Garching: TUM Campus Garching + SAP Labs
Munich (Garching) as commute anchors, warm rent <= 650 EUR, available by 2027-01-31, <= 30 min by
e-bike (22 km/h, routed), dashboard only (no Telegram). Branch `garching-cloudflare`.

## In flight

- First deploy to Cloudflare: needs `wrangler login` by the user, then D1 + queue creation, remote
  migration, deploy, `API_TOKEN` secret (runbook: `worker/README.md`).
- Confirm WG-Gesucht answers Cloudflare egress (only verified from a residential IP so far) and that
  a search-page parse stays inside the free plan's 10 ms CPU (check Workers Observability).

## Blocked

- Deploy is blocked on Cloudflare auth. 2026-10-23: `! cd worker && npx wrangler login` from inside
  Claude Code opened the OAuth page but timed out waiting for consent (the `!` command is
  backgrounded after 120 s); `wrangler whoami` still says the stored token expired. Fix: run
  `npx wrangler login` in your own terminal in `worker/` and approve in the browser within a minute
  or so, then the agent continues: `wrangler d1 create apartments` (paste `database_id` into
  `wrangler.jsonc`), `wrangler queues create apartment-jobs`, `npm run db:migrate:remote`,
  `npm run deploy`; the user sets `npx wrangler secret put API_TOKEN` themselves.

## Next up

- Second pass, porting from the retired Python pipeline: LLM fit ranking (free-first tiers),
  the markdown market wiki, feedback learning from dashboard triage. Then delete the Python package,
  `deploy/` (systemd, HF Space) and `.github/workflows/pages.yml`.

## Recently landed

- 2026-10-22 `worker/`: TypeScript Worker (cron + Queues + D1 + static dashboard with map), 49
  tests passing in workerd, live local run: 38 listings scraped, 12 matched.
- 2026-10-22 Python parser moved to selectolax's lexbor backend (selectolax 1.0 dropped the old
  one); legacy suite 93 passed / 1 skipped. The Python scraper still targets the pre-October card
  layout and returns 0 listings live: it is retired, not maintained.
- `b995c23` docs: project knowledge wiki at `docs/wiki/`.
