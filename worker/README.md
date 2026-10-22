# Garching flat hunt (Cloudflare Worker)

The live agent. One Worker scrapes WG-Gesucht every hour (05:00-22:00 UTC), keeps listings whose
warm rent is at most 650 EUR, available by 31 Jan 2027 and within a 30-minute e-bike ride
(22 km/h, routed) of both TUM Garching and SAP Garching, and serves a dashboard with a map.
Design and rejected alternatives:
[docs/wiki/decisions/cloudflare-workers-hosting.md](../docs/wiki/decisions/cloudflare-workers-hosting.md)
and [bike-time-filter.md](../docs/wiki/decisions/bike-time-filter.md).

```
cron / "Search now" ──► queue: search page ──► parse cards + map markers
                                             ├─ bike minutes (Valhalla matrix, estimate fallback)
                                             ├─ filter on card facts ──► D1 (rejected, with reasons)
                                             └─ queue: detail page ──► warm rent ──► filter ──► D1 (matched)
dashboard (public/) ◄── /api/* ◄── D1
```

Free plan throughout: Workers, D1, Queues, static assets.

## Develop

```sh
npm ci
npm test                      # vitest inside workerd, D1 migrations applied per run
npm run typecheck
npm run db:migrate:local
echo API_TOKEN=local-dev-token > .dev.vars
npm run dev                   # http://127.0.0.1:8787
curl "http://127.0.0.1:8787/cdn-cgi/handler/scheduled"   # trigger a run against the live site
```

## Deploy (once)

```sh
npx wrangler login
npx wrangler d1 create apartments          # put the printed database_id into wrangler.jsonc
npx wrangler queues create apartment-jobs
npm run db:migrate:remote
npm run deploy
npx wrangler secret put API_TOKEN          # any long random string; enter it in the dashboard's key dialog
```

Afterwards `npm run deploy` is enough. Reads are public at the `workers.dev` URL; to make the whole
page private, turn on Cloudflare Access for the Worker (dashboard: Workers & Pages -> the Worker ->
Settings -> Domains & Routes -> Enable Cloudflare Access).

## Change the criteria

All knobs are `vars` in `wrangler.jsonc` (anchors, rent cap, size, move-in date, minimum stay, bike
minutes and speed, page cap, manual-run cooldown, router URL). They are validated on every
invocation, so a typo fails loudly. After changing anchors, speed or minutes, regenerate the map
overlay with `node scripts/isochrone.mjs`. After changing the cron, update `SCHEDULE` in
`src/config.ts` (a test keeps them in sync). After changing bindings or vars, run `npm run types`.

## Operate

- Run history and errors: the status pill in the dashboard header, or `GET /api/runs`.
- A run marked **failed** with "0 cards parsed" means WG-Gesucht changed its HTML: update the
  selectors in `src/wggesucht.ts` and refresh `test/fixtures/` from a live page (anonymize lister
  names, photos and initials).
- Logs: `npx wrangler tail` or Workers Observability in the dashboard.
