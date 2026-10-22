---
type: decision
title: Filter on routed e-bike minutes to TUM and SAP Garching, not a radius
description: How "within 30 minutes by bike" is decided per listing, with the server-side radius derived as a guaranteed superset.
resource: worker/src/bike.ts
tags: [decision, search, geography, filter]
timestamp: 2026-10-22T00:00:00Z
---

## Context

The anchor moved from Alte Heide to Garching: the user studies at TUM Garching (CIT building,
Boltzmannstr. 3, `48.26255, 11.66804`) and may work at SAP Labs Munich (Friedrich-Ludwig-Bauer-Str. 5,
`48.26410, 11.66076`; both geocoded with Nominatim on 2026-10-22, about 0.6 km apart). The
requirement is "a 30-minute bike ride", which the user set as an **e-bike at about 22 km/h**.
The Isar, the A9 and the A99 make straight-line distance a poor proxy: route/straight-line ratios
measured on 2026-10-22 ranged from 1.16 (Alte Heide) to 1.36 (Dietersheim).

## What we chose

1. **Server-side superset.** The WG-Gesucht radius is derived, not configured:
   `speed x minutes + the farthest anchor's distance from the search centre`. A route can never be
   shorter than the straight line, so nothing reachable in time is outside the circle
   (11.6 km for 22 km/h x 30 min).
2. **Per-listing routed time.** Each new listing's coordinates (from the search page's `markers`
   JSON) go to Valhalla's `sources_to_targets` with `costing: bicycle`, `cycling_speed: 22`. The
   commute is the **slower of the two anchors**; the filter rejects above 30 min.
3. **Fallback estimate.** If the router fails, minutes = haversine x 1.3 / speed, stored with
   `bike_source = "estimate"` and shown as "~" in the UI, so routing outages never drop listings.

Routed from TUM on 2026-10-22 (Valhalla, 15 km/h profile): Garching centre 2.5 km, Dietersheim
3.6 km, Hochbrueck 6.0 km, Ismaning 6.2 km, Eching 7.0 km, Neufahrn 7.0 km, Unterschleissheim
9.4 km, Freimann 10.8 km, Studentenstadt 11.6 km, Alte Heide 12.5 km. At 22 km/h the 30-minute
line falls around Freimann / Studentenstadt.

## Alternatives & trade-offs

- **Straight-line radius** (the old Alte Heide design): no dependency, but it admits flats across
  the Isar with no nearby bridge and excludes nothing that is genuinely far by road.
- **Precomputed isochrone polygon + point-in-polygon**: no runtime dependency, but coarse and it
  cannot show the per-listing minutes the user decides on. It is kept only as a map overlay.
- **OpenRouteService**: comparable, but needs an API key; Valhalla's public FOSSGIS instance needs
  none. Its usage terms page was behind a bot wall on 2026-10-22, so calls are kept to one
  batched matrix request per search page (only for listings not seen before), with a descriptive
  `User-Agent`.
- **Where this is worse**: it depends on a free community server; an outage degrades to estimates
  rather than failing, which can admit or exclude a borderline listing by a few minutes.

## Revisit when

- The anchors change (new job or campus), or the user switches from e-bike to a normal bike
  (`BIKE_SPEED_KMH` 15 brings the line in to Eching / Neufahrn / Ismaning).
- The FOSSGIS instance rate-limits or blocks Worker traffic (switch to ORS with a key).

## Related pages

- [cloudflare-workers-hosting.md](cloudflare-workers-hosting.md)
- [radius-search.md](radius-search.md) - superseded by this page.
