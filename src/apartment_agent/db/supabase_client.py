"""Supabase (Postgres) access for listings: dedup lookups, upsert, notify marking."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apartment_agent.models import Listing

log = logging.getLogger(__name__)

TABLE = "listings"


def listing_to_row(listing: Listing) -> dict:
    """Map a Listing to a `listings` table row (JSON-serializable)."""
    return {
        "source": listing.source,
        "external_id": listing.external_id,
        "url": listing.url,
        "title": listing.title,
        "price_warm": listing.price_warm,
        "price_cold": listing.price_cold,
        "size_sqm": listing.size_sqm,
        "rooms": listing.rooms,
        "listing_type": listing.listing_type.value,
        "district": listing.district,
        "address": listing.address,
        "city": listing.city,
        "available_from": listing.available_from.isoformat() if listing.available_from else None,
        "available_to": listing.available_to.isoformat() if listing.available_to else None,
        "posted_at": listing.posted_at.isoformat() if listing.posted_at else None,
        "fit_score": listing.fit_score,
        "summary": listing.summary,
        "raw": listing.raw or {},
    }


class ListingsDB:
    def __init__(self, url: str, service_key: str):
        from supabase import create_client  # lazy: import/compile needs no creds

        self.client = create_client(url, service_key)

    def existing_external_ids(self, source: str, external_ids: list[str]) -> set[str]:
        """Which of these external_ids are already stored for the source."""
        if not external_ids:
            return set()
        resp = (
            self.client.table(TABLE)
            .select("external_id")
            .eq("source", source)
            .in_("external_id", external_ids)
            .execute()
        )
        return {row["external_id"] for row in (resp.data or [])}

    def upsert_listings(self, listings: list[Listing]) -> int:
        if not listings:
            return 0
        rows = [listing_to_row(x) for x in listings]
        self.client.table(TABLE).upsert(rows, on_conflict="source,external_id").execute()
        return len(rows)

    def mark_notified(self, source: str, external_ids: list[str]) -> None:
        if not external_ids:
            return
        now = datetime.now(timezone.utc).isoformat()
        (
            self.client.table(TABLE)
            .update({"notified_at": now})
            .eq("source", source)
            .in_("external_id", external_ids)
            .execute()
        )
