---
type: decision
title: Radius search vs city-wide + location allowlist
description: Constrain listings to a 5 km radius around a point instead of matching district names against an allowlist.
resource: src/apartment_agent/sources/wg_gesucht.py
tags: [decision, search, geography, filter]
timestamp: 2026-07-12T00:00:00Z
---

> **Superseded 2026-10-22** by [bike-time-filter.md](bike-time-filter.md): the anchor moved to Garching and routed e-bike minutes now decide.

## Context

The user wants flats near a specific spot (Alte Heide, north Munich), not "anywhere in Munich." Two ways to express "near": name the acceptable districts, or draw a circle.

## What we chose

A **geographic radius**: **5 km around Alte Heide** (lat `48.1783353`, lng `11.5978799`). WG-Gesucht's search accepts radius parameters, so this is applied **server-side** (`radAdd`/`radLat`/`radLng`/`radDis`). When a radius is set (`has_radius`), the [filter](../components/filter.md)'s location-allowlist rule is **skipped** entirely.

## How it works (beginner-first)

The scraper adds the radius params to the search URL, so WG-Gesucht only returns listings inside the circle — the geography constraint is enforced before the data ever reaches us. The old district-name allowlist still exists in `FilterConfig` but is only consulted in city-wide mode; with a radius it would be redundant, so it's bypassed.

## Alternatives & trade-offs

- **City-wide search + district-name allowlist**: no coordinates needed; easy to read ("these named neighborhoods"). **Trade-off**: district boundaries are arbitrary — a flat 300 m away across a district line is excluded, while a far corner of an "allowed" district is included. And it depends on the site labeling districts consistently (a substring match is brittle).
- **Where the chosen design is WORSE**: a radius is a **blunt circle** — it doesn't know that a river, rail line, or bad transit link makes an "in-radius" flat actually inconvenient, whereas hand-picked districts encode local knowledge. It also hard-codes a center point that must be updated if the user's anchor changes. We trade human geographic nuance for objective, boundary-independent distance.

## Why this serves the goal

"Near Alte Heide" is genuinely a distance, not a set of names. A radius expresses the real requirement directly and pushes the filtering to the server, cutting the volume we fetch and parse.

## Revisit when

- The user cares about specific named neighborhoods regardless of raw distance.
- Commute time (not straight-line distance) becomes the real constraint (needs routing, not a circle).

## Related pages

- Components: [scraper](../components/scraper.md), [filter](../components/filter.md)
