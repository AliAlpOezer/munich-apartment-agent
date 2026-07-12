---
type: concept
title: Warmmiete vs Kaltmiete (German rent, the critical domain concept)
description: What the German warm/cold rent distinction means and why the whole pipeline fetches a detail page to resolve it.
resource: src/apartment_agent/sources/wg_gesucht.py
tags: [domain, german, rent, scraping, beginner]
timestamp: 2026-07-12T00:00:00Z
---

## The one thing to internalize

A German rental listing quotes **two** different rent numbers, and mixing them up will silently corrupt every price filter. This is the single most important domain fact in the project.

- **Kaltmiete** ("cold rent") = the base rent for the flat, *nothing else*.
- **Nebenkosten** ("side costs" / **NK**) = the running extras: heating, water, building maintenance, garbage, etc.
- **Warmmiete** ("warm rent") = Kaltmiete **+** Nebenkosten. This is the number that actually leaves your bank account each month.

So: `Warmmiete = Kaltmiete + Nebenkosten`, and therefore `Warmmiete >= Kaltmiete` always.

## Why it matters here

The user's budget cap (**657 €**, see [current state](../state/current-state.md)) is a **warm-rent** cap — the real monthly cost. But a WG-Gesucht *search-result card* shows an ambiguous figure that is very often just the Kaltmiete. If you filtered the cap against the card number, you would let through flats whose true warm rent is well over budget.

## How the code models it

In [`models.py`](../components/orchestration.md) a `Listing` carries three price fields:

- `price_warm` — resolved Warmmiete (best).
- `price_cold` — Kaltmiete.
- `price_listed` — the ambiguous card figure. It is **transient**: not stored in the database, only used as a last-resort lower bound.

The property `effective_warm_rent` (`models.py:54-66`) returns the first of `price_warm`, `price_cold`, `price_listed` that exists. Because the fallbacks are all *lower bounds* (warm ≥ cold ≥ usually the card number), a listing can only be wrongly *let in* early, never wrongly excluded — and that is corrected once the detail page fills in `price_warm`.

## The resolution step

The pipeline therefore fetches each candidate's **detail page** and re-parses the true costs (`parse_detail_costs` in [`wg_gesucht.py`](../components/scraper.md)), then re-runs the [filter](../components/filter.md). Two hard-won guards live there:

- It reads label→value **pairs** (e.g. the value next to "Miete"), *not* a whole-row scan — a whole-row scan concatenated unrelated numbers into wildly wrong prices.
- A floor `_MIN_PLAUSIBLE_RENT_EUR = 50` rejects placeholder rents like "2 €" (Nebenkosten is exempt from the floor). Shipped in commit `48f4cc7`.

## Related pages

- Decision: [resolve true Warmmiete via a detail-page fetch](../decisions/warmmiete-detail-fetch.md)
- Component: [scraper](../components/scraper.md), [filter](../components/filter.md)
