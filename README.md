# Munich apartment agent

A small agent that watches Munich listing sites for rooms and flats within reach of TUM Garching
and shows the ones that fit on a map. It exists because good offers in Munich are often gone
within hours, and checking two sites by hand several times a day does not scale.

It runs as a single Cloudflare Worker on the free plan: no server, no database to host, nothing to
keep alive. Live at https://apartment-agent.alialp.workers.dev.

## What it looks for

| Criterion | Value |
|---|---|
| Sources | WG-Gesucht, Kleinanzeigen (rooms, flats, houses) |
| Warm rent | at most 650 EUR |
| Room or flat size | at least 10 m² |
| Move-in | available by 31 Jan 2027, staying at least 90 days |
| Commute | at most 37 min by e-bike to TUM Garching, **or** at most 10 min to a U6 station between Garching-Forschungszentrum and Nordfriedhof |
| Excluded | flat swaps (Tausch) |

Every value is a setting in [`worker/wrangler.jsonc`](worker/wrangler.jsonc), checked at startup so
a typo fails loudly instead of filtering the wrong way.

## How it works

```
hourly cron / "Search now"
        │
        ▼
  queue: search page ──► parse listing cards and map coordinates
                         ├─ route e-bike minutes (Valhalla, estimate if it is down)
                         ├─ filter on card facts ───────────────► D1: rejected, with reasons
                         └─ queue: detail page ──► warm rent ──► D1: matched
                                                                    │
  dashboard (map, cards, triage) ◄── /api ◄─────────────────────────┘
```

1. **Search.** Every hour between 05:00 and 22:00 UTC, the Worker queues one result page per
   search stream. Pages are fetched one at a time through a queue, which keeps the load on the
   sites low and the Worker well inside its CPU limit.
2. **Locate.** WG-Gesucht puts each listing's coordinates on the search page; Kleinanzeigen puts
   them on the detail page, which is fetched first. The coordinates are sent to a public
   [Valhalla](https://valhalla.github.io/valhalla/) routing server, which returns real cycling
   minutes to TUM and to each U6 station. Straight-line distance is a poor proxy here: the Isar and
   the motorways make some routes over a third longer than the crow flies.
3. **Filter.** Rent, size, dates and commute are checked on what the search card shows. A listing
   that fails is stored with its reasons, so the dashboard can explain every rejection.
4. **Confirm the rent.** Cards often show only the cold rent. For listings that pass, the detail
   page is fetched once to read the warm rent before the final decision.
5. **Show.** The dashboard lists matches as cards and pins on a map, with the reachable area shaded.
   Each listing can be marked new, interested or dismissed.

A few rules keep the results trustworthy:

- **The search area is a guaranteed superset.** The radius sent to each site is derived from the
  commute limits, and a route is never shorter than a straight line, so nothing reachable is cut
  off server-side. The precise decision happens per listing.
- **Outages degrade, they do not drop listings.** If the router is down, the commute is estimated
  from distance, marked with "~" on the card, and re-routed the next time the listing appears.
- **Criteria changes apply retroactively.** Each decision records the criteria it was made under.
  After a change, listings still online are re-decided on their next sighting, and their triage is
  kept.

## Repository layout

| Path | Contents |
|---|---|
| [`worker/`](worker/README.md) | The live agent: TypeScript Worker, D1 migrations, dashboard, tests. Setup and operations are in its README. |
| [`docs/context/`](docs/context/INDEX.md) | Short context pack: current status, architecture, decisions, known gotchas. |
| [`docs/wiki/`](docs/wiki/index.md) | Longer design records, each with the alternatives that were rejected and why. |
| `src/`, `tests/`, `deploy/` | The earlier Python version, kept for reference (see below). |

## Running it

```sh
cd worker
npm ci
npm test            # runs inside workerd with a fresh local D1
npm run dev         # http://127.0.0.1:8787
```

First-time deployment, criteria changes and troubleshooting are covered in
[`worker/README.md`](worker/README.md).

## Not done yet

- The same flat posted on both sites appears twice.
- No notifications: the dashboard is the only output.
- Ranking by fit, a written summary of the market, and learning from triage decisions existed in
  the Python version and are still to be ported.

## The earlier Python version

The agent started as a Python [LangGraph](https://langchain-ai.github.io/langgraph/) pipeline on a
home server: scrape every three hours, deduplicate in SQLite, rank listings with a tiered set of
LLMs (free models first, paid ones only when needed), keep a markdown wiki of the market, and send
matches to Telegram. It was retired in October 2026 when WG-Gesucht changed its page layout and the
search moved to Garching. The code is still in `src/apartment_agent/` until its useful parts are
ported, but it is no longer maintained and its scraper no longer finds listings.

## Disclaimer

A personal, low-frequency tool for one apartment search. Listing data is not redistributed.
Scraping may conflict with a site's terms of service, so keep request rates gentle.
