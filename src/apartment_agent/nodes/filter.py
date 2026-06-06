"""Hard filtering of listings.

Pure functions, no I/O, fully unit-tested. The policy is intentionally explicit and
slightly *permissive on missing data* — we would rather surface a listing for review
than silently drop a possible match because a field failed to parse.

Filter rules (all must pass):
  1. Warm rent <= max_warm_rent_eur.
       - Uses Warmmiete if known, else Kaltmiete as a permissive lower bound.
       - If neither is known: keep (flagged), since rent is the whole point and a
         missing value usually means a parse miss, not "free".
  2. Size >= min_size_sqm.  Unknown size: keep (flagged).
  3. available_from within [move_in - before_grace, move_in + after_window].
       - Undated ("ab sofort" / unparsed): rejected (we want a specific move-in match).
       - Also rejects sublets that end before the move-in date.
       (Listing categories are controlled by the search URL, so type is not re-checked.)
  4. Location matches one of the allowed substrings (checks district/address/city).
       - No location text at all: keep (flagged).
"""

from __future__ import annotations

from datetime import timedelta

from apartment_agent.models import FilterConfig, Listing


def passes_filter(listing: Listing, cfg: FilterConfig) -> tuple[bool, list[str]]:
    """Return (passed, reasons). `reasons` lists why it was rejected (empty if passed)."""
    reasons: list[str] = []

    # 1. Rent
    rent = listing.effective_warm_rent
    if rent is not None and rent > cfg.max_warm_rent_eur:
        reasons.append(f"rent {rent:.0f}€ > {cfg.max_warm_rent_eur:.0f}€")

    # 2. Size
    if listing.size_sqm is not None and listing.size_sqm < cfg.min_size_sqm:
        reasons.append(f"size {listing.size_sqm:.0f}m² < {cfg.min_size_sqm:.0f}m²")

    # 3. Availability around the move-in date. The search already filters "from move_in onward"
    #    (WG-Gesucht dFr); this enforces the window locally and drops undated / far-future listings.
    #    (Listing type / categories are controlled by the search URL, so not re-checked here.)
    earliest = cfg.move_in_date - timedelta(days=cfg.available_from_before_grace_days)
    latest = cfg.move_in_date + timedelta(days=cfg.available_from_after_window_days)
    if listing.available_from is None:
        reasons.append("no available-from date")
    elif listing.available_from < earliest:
        reasons.append(f"available_from {listing.available_from} before {earliest}")
    elif listing.available_from > latest:
        reasons.append(f"available_from {listing.available_from} after {latest}")
    if listing.available_to is not None and listing.available_to < cfg.move_in_date:
        reasons.append(f"sublet ends {listing.available_to} before move-in")

    # 5. Location
    haystack = " ".join(
        part.lower() for part in (listing.district, listing.address, listing.city) if part
    )
    if haystack and not any(loc in haystack for loc in cfg.allowed_locations):
        reasons.append("location not in allowed area")

    return (len(reasons) == 0, reasons)


def filter_listings(
    listings: list[Listing], cfg: FilterConfig
) -> tuple[list[Listing], list[tuple[Listing, list[str]]]]:
    """Split listings into (matched, rejected_with_reasons)."""
    matched: list[Listing] = []
    rejected: list[tuple[Listing, list[str]]] = []
    for listing in listings:
        ok, reasons = passes_filter(listing, cfg)
        if ok:
            matched.append(listing)
        else:
            rejected.append((listing, reasons))
    return matched, rejected
