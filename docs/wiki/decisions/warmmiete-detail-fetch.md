---
type: decision
title: Resolve true Warmmiete via a detail-page fetch + re-filter
description: Trust neither the ambiguous list-card price nor a guess — fetch the detail page, parse the real warm rent, then filter again.
resource: src/apartment_agent/sources/wg_gesucht.py
tags: [decision, scraping, rent, filter]
timestamp: 2026-07-12T00:00:00Z
---

## Context

The user's budget cap of **657 €** is a **warm** rent (see [Warmmiete vs Kaltmiete](../concepts/warmmiete-vs-kaltmiete.md)). But the number on a WG-Gesucht search-result card is ambiguous and often just the Kaltmiete (base rent), which is lower than the real monthly cost.

## What we chose

Treat the card price as a **transient lower bound** (`price_listed`), then **fetch each candidate's detail page**, parse the true `Warmmiete` (`parse_detail_costs`), and **re-run the filter** against the resolved number.

## How it works (beginner-first)

1. The card parser stores the card figure as `price_listed`.
2. `effective_warm_rent` (`models.py:54`) prefers `price_warm`, then `price_cold`, then `price_listed` — all lower bounds, so the pre-filter is *permissive* (it may let a too-expensive flat through, never wrongly exclude one).
3. The `detail` node fetches the page and fills `price_warm = cold + extras`.
4. The filter runs again against the now-accurate number. Over-budget flats drop out here.

Two guards live in the parser: value-per-element parsing (not a whole-row scan that concatenated unrelated numbers), and a `_MIN_PLAUSIBLE_RENT_EUR = 50` floor that rejects placeholder "2 €" rents (commit `48f4cc7`).

## Alternatives & trade-offs

- **Trust the list card**: no extra requests, much faster. **Trade-off**: systematically wrong — you'd notify on flats whose true warm rent is well over budget, eroding trust in every alert.
- **Guess NK as a fixed % of cold rent**: cheap, no fetch. **Trade-off**: Munich Nebenkosten varies widely; a fixed multiplier is wrong often enough to leak bad listings or hide good ones.
- **Where the chosen design is WORSE**: it costs **N extra HTTP requests per run** (one per candidate, at `detail_concurrency=3`), making runs slower and more detectable as a bot; and the detail parser is fragile HTML-scraping that breaks when WG-Gesucht changes layout. We accept slower, more brittle runs to get correct prices.

## Why this serves the goal

An alert the user can't trust is worse than no alert. Price correctness is the product; the extra latency is affordable for a 3-hourly job.

## Revisit when

- WG-Gesucht exposes warm rent reliably on the card (then skip the fetch).
- Detail-page volume triggers blocking (throttle harder or fetch lazily).

## Related pages

- Concept: [Warmmiete vs Kaltmiete](../concepts/warmmiete-vs-kaltmiete.md)
- Components: [scraper](../components/scraper.md), [filter](../components/filter.md)
