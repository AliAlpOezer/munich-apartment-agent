"""Core data models shared across the graph.

Kept dependency-light (pydantic + stdlib only) so the filter and its tests can run
without scraping/LLM/DB extras installed.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ListingType(StrEnum):
    WG_ROOM = "wg_room"        # a room in a shared flat (Wohngemeinschaft)
    APARTMENT = "apartment"    # a whole flat (1-Zimmer-Wohnung / Wohnung)
    UNKNOWN = "unknown"


class Listing(BaseModel):
    """A single normalized housing listing."""

    source: str                                   # e.g. "wg_gesucht"
    external_id: str                              # site-native id; unique per source
    url: str
    title: str | None = None

    price_warm: float | None = None               # Warmmiete (incl. utilities), EUR/month
    price_cold: float | None = None               # Kaltmiete (excl. utilities), EUR/month
    # The single figure shown on a search-result card. Its basis is ambiguous (often Kaltmiete),
    # so it is kept distinct from warm/cold and used only as a permissive pre-filter proxy until
    # the detail page resolves the real warm/cold split. Transient: not persisted to the DB.
    price_listed: float | None = None
    size_sqm: float | None = None
    rooms: float | None = None
    listing_type: ListingType = ListingType.UNKNOWN

    district: str | None = None                   # Stadtteil / area
    address: str | None = None
    city: str | None = None

    available_from: date | None = None            # "frei ab"
    available_to: date | None = None              # set for temporary sublets (Zwischenmiete)
    posted_at: datetime | None = None

    # LLM enrichment (tier2/tier3), filled later
    fit_score: int | None = None
    summary: str | None = None

    # Whatever the parser couldn't normalize, kept for debugging / re-parsing
    raw: dict = Field(default_factory=dict)

    @property
    def effective_warm_rent(self) -> float | None:
        """Best available figure to compare against the warm-rent cap.

        Prefer the resolved Warmmiete; fall back to Kaltmiete, then to the ambiguous list-card
        figure. Both fallbacks are permissive lower bounds (Warmmiete >= Kaltmiete, and the listed
        figure is usually Kaltmiete), so a too-low pre-filter is corrected once the detail page
        populates `price_warm`.
        """
        for value in (self.price_warm, self.price_cold, self.price_listed):
            if value is not None:
                return value
        return None


class FilterConfig(BaseModel):
    """Hard search filters. Pure data so the filter function is easy to unit-test."""

    max_warm_rent_eur: float = 700.0
    min_size_sqm: float = 12.0
    move_in_date: date = date(2026, 10, 1)
    # available_from must fall within [move_in - before_grace, move_in + after_window].
    # before_grace: places freeing up slightly early that you could still take.
    # after_window: how far past the move-in date is still acceptable (drops far-future listings).
    available_from_before_grace_days: int = 14
    available_from_after_window_days: int = 92
    listing_types: set[ListingType] = Field(
        default_factory=lambda: {ListingType.WG_ROOM, ListingType.APARTMENT}
    )
    # Lowercased substrings that an acceptable location must match (city + commutable belt).
    allowed_locations: list[str] = Field(
        default_factory=lambda: [
            "münchen", "munchen", "munich",
            "garching", "freising", "dachau", "fürstenfeldbruck", "furstenfeldbruck",
            "unterföhring", "unterfohring", "ismaning", "oberschleißheim",
            "germering", "puchheim", "olching", "gröbenzell", "grobenzell",
            "haar", "ottobrunn", "unterhaching", "taufkirchen", "planegg",
            "gauting", "starnberg", "vaterstetten", "markt schwaben", "erding",
        ]
    )


class RunResult(BaseModel):
    """Summary of a single scheduled run, for logging/heartbeat."""

    scraped: int = 0
    parsed: int = 0
    matched: int = 0
    new: int = 0
    notified: int = 0
    errors: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
