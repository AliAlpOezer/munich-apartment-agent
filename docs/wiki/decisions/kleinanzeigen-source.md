---
type: decision
title: Kleinanzeigen as a second listing source behind a source seam
description: How the Worker searches Kleinanzeigen next to WG-Gesucht - source adapters, search streams, a page frontier, detail-stage routing - and what was measured to justify it.
resource: worker/src/sources.ts
tags: [decision, scraping, sources, pipeline, cpu]
timestamp: 2026-10-23T00:00:00Z
---

## Goal

Show every rentable place that fits the Garching rules (rent, size, dates, commute) on the one
dashboard, whichever of the two big Munich sites it was posted on, decided by the same rules.

## Evidence (checked 2026-10-23)

- **Cloudflare egress works.** A throwaway Worker run with `wrangler dev --remote` fetched two
  search pages and a detail page: HTTP 200, real content, no challenge. Akamai Bot Manager fronts the
  site (`_abck`, `bm_sz` cookies) but lets the plain fetch with browser headers through.
- **Search pages carry no coordinates.** Cards (`article[data-adid]`) give zip + district, km from
  the search centre, title, a facts line (`9 m² · 3 Zi.`), the current price and sometimes a
  struck-through old price. The detail page has `og:latitude` / `og:longitude`.
- **Gesuche are mixed in.** 39 of 97 WG results and 77 of 325 flat results were wanted ads; their
  facts line starts with `Gesuch ·`. The "offers only" facet (`/anzeige:angebote/`) is disallowed by
  robots.txt, so they are dropped per card.
- **Swaps are common.** 6 of the first 25 flat cards were swaps ("Wohnungsswap", "TAUSCHWOHNUNG").
  A swap needs a flat to give in exchange. One swap ad had no `Tauschangebot` attribute, only the
  title said so.
- **Paging is a sliding window.** Page 1 of 13 links to pages 2-5 only.
- **Other places pad short lists.** Below the results, `ul#srchrslt-adtable-altads` ("Weitere
  Ergebnisse in anderen Orten") lists ads up to 30 km away. A search with no results says "Es wurden
  keine Ergebnisse ... gefunden" in `#srp-breadcrumb-summary`.
- **The ad-targeting JSON disagrees with the page.** On one detail page it said `Wohnflaeche: 160`
  while the visible attribute list said 9 m². Only visible fields are parsed.
- **Pages are large and CPU is tight.** Search 720-745 KB, detail ~285 KB (WG-Gesucht's fixture is
  45 KB). Local workerd, per parse: HTMLRewriter 34.6 ms on a search page (30.7 ms on just the card
  slice, so the cost is in the handlers, not the bytes), string scanning per card 4.8 ms, detail
  scan 0.5 ms, UTF-8 decode of 726 KB 5.2 ms. The free plan allows 10 ms CPU per invocation.
- **Edge CPU, measured on Cloudflare.** A throwaway Worker parsed the bundled full-size captures with
  the shipped adapter; `wrangler tail --format json` reports `cpuTime` per event. After a warm-up:
  search page median 4 ms (3-9, n=14), detail page median 2 ms (0-3, n=13). Local timings do not
  transfer: the same search page took 13 ms locally.

## Invariants

1. **One rule set.** `filter.ts` decides every listing from facts; adapters only produce facts.
   Nothing source-specific reaches the filter.
2. **No decision before the facts exist.** A listing whose position only the detail page has stays
   `pending_detail` until that page is read. "Ride unknown" means the page had no position, never
   "not looked yet".
3. **Success is observed per stream.** A 200 page with no parseable cards that does not say it has no
   results is a failed page, recorded under its stream. One source failing never stops or hides the
   other.
4. **Each page is fetched once per run.** A page is claimed (`run_pages` row, status `queued`) in the
   same step that enqueues it, under `PRIMARY KEY (run_id, stream, page)`. Redelivered pages and
   overlapping windows cannot enqueue it twice.
5. **Polite by construction.** All fetches go through the one queue consumer (concurrency 1) with
   spacing; only paths robots.txt allows are requested.

## What we chose

| Component | Owns | Reason to change |
|---|---|---|
| `wggesucht.ts`, `kleinanzeigen.ts` | URLs, allowlist, card and detail parsing for one site | that site's markup |
| `sources.ts` | the `Source` contract and the registry | a new kind of fact |
| `pipeline.ts` | runs, streams, frontier, routing, decisions | orchestration |
| `filter.ts` | rules (new: swap) | the user's criteria |

- **Search streams.** A run fetches one result list per (source, category): `wg_gesucht`,
  `kleinanzeigen:wohnung` (c203), `kleinanzeigen:wg` (c199, Auf Zeit & WG), `kleinanzeigen:haus`
  (c205). The `SOURCES` var switches sources on and off without a code change.
- **Page frontier, not a page count.** Every page enqueues the linked pages below `MAX_PAGES` that
  are not claimed yet. A run is done when no page is `queued` and no listing is pending. This
  replaces `runs.pages_total`.
- **Card facts vs detail facts.** A source declares which facts only its detail page has
  (Kleinanzeigen: position, availability). When a known listing is re-decided from its card, those
  facts come from the stored row.
- **Detail-stage routing.** When a detail page supplies a position the row lacks, the detail job
  routes it (one 1 x 11 matrix call) before deciding. Estimates are re-routed on the next sighting,
  as before.
- **String scanning for Kleinanzeigen.** The adapter decodes the page once, cuts the main result list
  out by its ids, and scans each `<article>` with small patterns, classifying texts by shape (zip +
  place, `(N km)`, facts line, price) rather than Tailwind classes.
- **Search geometry.** Kleinanzeigen searches around location 6303 (Garching b München, centre
  48.2488, 11.6511). Radius = the derived bike/U6 radius plus the centre's offset from the anchors,
  rounded up to whole km, so it stays a superset. `preis::<max warm rent>` is safe server-side
  because the listed price is cold or warm, never above warm.
- **Room size in "Auf Zeit & WG".** The area there is the room's or the whole flat's as the lister
  likes ("9 m² · 3 Zi." and "200 m² · 10 Zi." on one page). Above 40 m² with more than one room it
  is taken as the flat's: shown in the label ("3 Zi., 55 m² flat"), not used as the room size, so it
  neither tops the "Biggest room" sort nor fakes a 2 EUR/m² price.
- **Swaps are rejected** (`swap` fact: title pattern OR the detail `Tauschangebot` attribute), with
  a visible reason. The rule applies to both sources. `RULES_REVISION` is hashed into the criteria
  version, so a rule change re-decides listings still online.

## Failure model

- Akamai starts challenging Cloudflare egress: Kleinanzeigen pages fail visibly (HTTP 403 or zero
  cards), WG-Gesucht carries on; set `SOURCES` to drop it.
- Detail page fails three times: decided on card facts. For Kleinanzeigen that means ride unknown,
  so it is kept (permissive rule) and shown without a ride.
- Detail page redirects off `/s-anzeige/` (ad deleted): rejected as no longer online.
- Router down in a detail job: haversine estimate, re-routed on the next sighting.
- CPU limit exceeded: the queue retries, then drops the message; the page stays `queued` and the run
  shows as stalled.

## Rejected alternatives

- **The "Angebote" facet URL.** Disallowed by robots.txt.
- **Ad-targeting JSON on detail pages.** It is early in the page and machine-shaped, but it disagreed
  with the visible page (160 vs 9 m²).
- **Zip-centroid table to route at search time.** More data to maintain, and the detail page has a
  better position one stage later anyway.
- **Page-0 enumeration (the WG-Gesucht approach).** Kleinanzeigen links a sliding window.
- **Encoding the stream into the page number** to avoid a migration. Hidden coupling in the key.
- **HTMLRewriter for Kleinanzeigen.** About 7x the CPU of string scanning on these pages.
- **Decoding only the second half of the page.** A Boyer-Moore-Horspool byte search in JS to skip
  the first 50% before decoding measured slower on the edge (median 10.5 ms vs 5.0 ms for decoding
  everything in the same deployment): V8's native UTF-8 decoder beats JS over 370 KB. Instead,
  regexes run only over the windows they need (summary element, pager after the last card).
- **A second Worker per source.** Duplicates queue, store and dashboard for no new capability.
- **Workers Paid.** Not needed at a 4 ms median; it stays the fallback if 1102 errors show up.

## Open

- Cross-source duplicates: the same flat posted on both sites shows twice.
- Swaps are rejected by default. In the first live run (local, 2026-10-23) they were 102 of 240
  Kleinanzeigen listings, every one titled "TAUSCHWOHNUNG" (55) or "Wohnungsswap" (47). If the user
  has a Munich flat to swap, flip the rule.
- Short stays priced per night (e.g. "29 €" for a few weeks) have no structured end date; the price
  falls under the 50 EUR plausibility floor and the listing is kept for triage.
