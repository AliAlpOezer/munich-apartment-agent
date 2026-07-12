---
type: component
title: Filter node
description: Pure, tested rules that decide whether a listing matches the user's cap, size, move-in window, and (city-wide only) location.
resource: src/apartment_agent/nodes/filter.py
tags: [component, filter, pure-function, tested]
timestamp: 2026-07-12T00:00:00Z
---

## What it does

Decides whether each scraped listing is a keeper. It is **pure** (no I/O, no network — output depends only on inputs) and fully unit-tested, which is the point: the business logic that gates everything downstream must be deterministic and cheap to verify.

## Where it lives

`src/apartment_agent/nodes/filter.py`.

## Interface

- `passes_filter(listing: Listing, cfg: FilterConfig) -> tuple[bool, list[str]]` (`filter.py:30`) — returns pass/fail plus human-readable reasons for any rejection.
- `filter_listings(...)` — maps `passes_filter` over a list.

## Rules (current)

1. **Rent**: `effective_warm_rent <= cap` (cap = 657 €). Uses the [Warmmiete lower bound](../concepts/warmmiete-vs-kaltmiete.md).
2. **Size**: `size_sqm >= min` (min = 10 m²). **Unknown size is KEPT.**
3. **Move-in window**: `available_from` must fall in `[move_in − 14 days, move_in + 92 days]`. **Undated listings are REJECTED.** A sublet whose end date is before move-in is rejected.
4. **Location**: substring allowlist match — but **SKIPPED entirely when `has_radius`** is true (the radius search already constrains geography; see [radius search decision](../decisions/radius-search.md)).

## Design philosophy: "permissive on missing data"

Unknown rent, unknown size, and (city-wide mode) unknown location are all **kept**, because a missing field is usually a parse miss, not a genuinely bad listing — and the [detail fetch](../concepts/warmmiete-vs-kaltmiete.md) often fills it in later. **Dates are the deliberate exception**: an undated listing is rejected, because move-in timing is non-negotiable for the user and cannot be safely guessed.

## Config / Settings keys that tune it

Via `FilterConfig` (built by `Settings.filter_config()`):
- `max_warm_rent_eur` (657.0), `min_size_sqm` (10.0), `move_in_date` (2026-09-01).
- Window constants `available_from_before_grace_days=14`, `available_from_after_window_days=92`.
- `listing_types`, `allowed_locations` (city-wide only), radius fields + `has_radius`.

## Related pages

- Concept: [Warmmiete vs Kaltmiete](../concepts/warmmiete-vs-kaltmiete.md)
- Decision: [radius search vs city-wide + allowlist](../decisions/radius-search.md)
- Pipeline neighbours: [scraper](scraper.md) → filter → [database dedup](database.md)
