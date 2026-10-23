---
type: decision
title: Filter on routed e-bike minutes to TUM and SAP Garching, or a short ride to the U6
description: How the commute rule (37 min by e-bike, or 10 min to a U6 station) is decided per listing, with the server-side radius derived as a guaranteed superset.
resource: worker/src/bike.ts
tags: [decision, search, geography, filter]
timestamp: 2026-10-23T00:00:00Z
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

## Update 2026-10-23: 37 minutes, or 10 minutes to the U6

The user widened the area:

- **Bike limit 30 -> 37 min** (slower anchor), to take in Oberschleissheim and Unterschleissheim.
  Routed at 22 km/h on 2026-10-23, slower anchor: Oberschleissheim centre 30.5, south 34.5, west
  35.9; Unterschleissheim centre 31.7, west 36.4, Lohhof 36.9. Side effect accepted: places at the
  same distance qualify too (Unterfoehring, Hallbergmoos, Fahrenzhausen, north Milbertshofen).
- **Alternative commute: <= 10 min by e-bike to any U6 station** from Garching-Forschungszentrum
  to Nordfriedhof (9 stations, coordinates from OSM station nodes, 2026-10-23). The stops are
  extra targets in the same matrix request; the nearest one is stored per listing
  (`stop_label`, `stop_minutes`). A listing passes if either commute fits.
- **Derived radius** now covers both: max(anchor spread + 37 min x 22 km/h, farthest stop + 10 min
  x 22 km/h) = 14.9 km (Nordfriedhof dominates). That is 118 listings / 6 pages at <= 650 EUR.
- **Criteria changes apply retroactively**: each decision stores a hash of the criteria; a
  listing decided under another version (or whose ride is still an estimate) is re-decided the
  next time it appears on a search page, keeping its triage and reusing an already-resolved rent.

First run under these rules (2026-10-23 11:55 UTC): 116 scraped, 45 matched, 25 of them only via
the U6 (mostly Schwabing / Maxvorstadt within 10 min of Nordfriedhof).

The FOSSGIS instance caps a matrix at **100 source x target pairs** (error_code 150). With 11
targets that first run's requests were refused and every ride fell back to an estimate without
failing the run; requests are now chunked to fit, a router failure is noted in the run history, and
estimated rides are re-routed on the next sighting.

## Alternatives & trade-offs

- **Straight-line radius** (the old Alte Heide design): no dependency, but it admits flats across
  the Isar with no nearby bridge and excludes nothing that is genuinely far by road.
- **Precomputed isochrone polygon + point-in-polygon**: no runtime dependency, but coarse and it
  cannot show the per-listing minutes the user decides on. It is kept only as a map overlay.
- **OpenRouteService**: comparable, but needs an API key; Valhalla's public FOSSGIS instance needs
  none. Its usage terms page was behind a bot wall on 2026-10-22, so calls are kept to batched
  matrix requests (at most 100 pairs each) per search page (only for listings not seen before), with a descriptive
  `User-Agent`.
- **Per-town exception for Ober-/Unterschleissheim** (2026-10-23): rejected, because matching
  town names in card text is the brittle allowlist this page replaced; one global limit is simple
  and explainable, at the cost of admitting other places at the same distance.
- **Where this is worse**: it depends on a free community server; an outage degrades to estimates
  rather than failing, which can admit or exclude a borderline listing by a few minutes.

## Revisit when

- The anchors change (new job or campus), or the user switches from e-bike to a normal bike
  (`BIKE_SPEED_KMH` 15 brings the line in to Eching / Neufahrn / Ismaning).
- The FOSSGIS instance rate-limits or blocks Worker traffic (switch to ORS with a key).

## Related pages

- [cloudflare-workers-hosting.md](cloudflare-workers-hosting.md)
- [radius-search.md](radius-search.md) - superseded by this page.
