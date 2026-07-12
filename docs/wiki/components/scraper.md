---
type: component
title: Scraper (WG-Gesucht adapter)
description: Fetches and parses Munich WG-Gesucht search results and detail pages, using TLS impersonation with a headless-browser fallback.
resource: src/apartment_agent/sources/wg_gesucht.py
tags: [component, scraper, wg-gesucht, curl-cffi, playwright]
timestamp: 2026-07-12T00:00:00Z
---

## What it does

Builds the WG-Gesucht search URL from the current filter config, downloads the result pages while pretending to be a real Chrome browser, parses each listing card, and (for candidates) fetches the detail page to resolve the true [Warmmiete](../concepts/warmmiete-vs-kaltmiete.md).

## Where it lives

- `src/apartment_agent/sources/base.py` — `SourceAdapter` abstract base class (ABC), so more sites can be added behind the same interface.
- `src/apartment_agent/sources/wg_gesucht.py` — `WgGesuchtAdapter`.

Constants: `MUNICH_CITY_ID = 90`, `request_delay = 2.5` seconds between requests (human-ish pacing).

## Interface

- `SourceAdapter` (ABC) — the contract every source implements.
- `WgGesuchtAdapter.build_search_urls(...)` — one combined URL over the 4 WG-Gesucht categories, with `rMax=<cap>`, `dFr=<move-in as epoch>` (available-from onward), newest-first sort, `offer_filter`, `noDeact`; adds `radAdd`/`radLat`/`radLng`/`radDis` when `has_radius`. **Size is NOT filtered server-side** (done later in the [filter](filter.md)).
- Card parser — `selectolax` over `div[data-id]`; stores the card price as `price_listed` (the ambiguous figure).
- `parse_detail_costs(...)` — reads label→value **pairs** (structured first, then a generic fallback; a generic "miete" is matched last), and derives `warm = cold + extras`.

## Current implementation

- **HTTP client**: `curl_cffi` with `impersonate="chrome"` — mimics a real Chrome TLS fingerprint. Plain `requests` gets blocked by WG-Gesucht, which is why this is not optional. Wrapped in `@network_retry` (see [resilience decision](../decisions/resilience-and-safety.md)).
- **Fallback**: a headless-Chromium **Playwright** path (the sync API run on worker threads) is used only if `curl_cffi` fails *and* the optional `[browser]` extra is installed; otherwise the original error is re-raised. See [TLS-impersonation scraping decision](../decisions/tls-impersonation-scraping.md).

### Two resolved bugs worth remembering
- **Value-per-element, not whole-row scan**: an earlier whole-row scan concatenated unrelated numbers into wildly wrong prices; the fix reads the value next to each label.
- **Plausibility floor** `_MIN_PLAUSIBLE_RENT_EUR = 50`: rejects placeholder detail-page rents like "2 €" (Nebenkosten is exempt). Commit `48f4cc7`.

## Config / Settings keys that tune it

- `search_center_lat` / `search_center_lng` / `search_radius_m` (default 5000) → radius params.
- `max_warm_rent_eur` (657) → `rMax`.
- `move_in_date` (2026-09-01) → `dFr`.
- `listing_types` → which of the 4 categories to include.
- `enable_detail_fetch` (True) and `detail_concurrency` (3) → whether/how many detail pages to fetch in parallel.

## Related pages

- Concept: [Warmmiete vs Kaltmiete](../concepts/warmmiete-vs-kaltmiete.md)
- Decisions: [TLS-impersonation scraping](../decisions/tls-impersonation-scraping.md), [resolve Warmmiete via detail fetch](../decisions/warmmiete-detail-fetch.md), [radius search](../decisions/radius-search.md)
- Next in pipeline: [filter](filter.md)
