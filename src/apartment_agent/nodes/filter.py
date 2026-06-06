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
  3. Listing type in the configured set (UNKNOWN is allowed through).
  4. Availability overlaps the move-in date:
       - Not a sublet that already ends before move-in (available_to >= move_in).
       - Becomes available by move_in + window (available_from <= move_in + window).
       - Unknown dates: keep.
  5. Location matches one of the allowed substrings (checks district/address/city).
       - No location text at all: keep (flagged).
"""

from __future__ import annotations

from datetime import timedelta

from apartment_agent.models import FilterConfig, Listing, ListingType


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

    # 3. Type
    if (
        listing.listing_type is not ListingType.UNKNOWN
        and listing.listing_type not in cfg.listing_types
    ):
        reasons.append(f"type {listing.listing_type.value} not wanted")

    # 4. Availability window
    latest_ok_start = cfg.move_in_date + timedelta(days=cfg.available_from_window_days)
    if listing.available_to is not None and listing.available_to < cfg.move_in_date:
        reasons.append(f"sublet ends {listing.available_to} before move-in {cfg.move_in_date}")
    if listing.available_from is not None and listing.available_from > latest_ok_start:
        reasons.append(
            f"available_from {listing.available_from} later than {latest_ok_start}"
        )

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
