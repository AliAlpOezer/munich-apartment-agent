"""Supabase (Postgres) access for listings: dedup lookups, upsert, notify marking."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from apartment_agent.models import Listing, ListingType, RunResult

log = logging.getLogger(__name__)

TABLE = "listings"
RUNS_TABLE = "runs"


def run_to_row(r: RunResult) -> dict:
    """Map a RunResult to a `runs` table row (JSON-serializable)."""
    return {
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "duration_ms": r.duration_ms,
        "scraped": r.scraped,
        "matched": r.matched,
        "new": r.new,
        "notified": r.notified,
        "errors": len(r.errors),
        "tokens": r.tokens or {},
        "node_timings_ms": r.node_timings_ms or {},
        "error_detail": r.errors,
    }


def _as_date(value) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) and value else None


def row_to_listing(row: dict) -> Listing:
    """Inverse of `listing_to_row` — rebuild a Listing from a stored row (for the wiki corpus)."""
    return Listing(
        source=row["source"],
        external_id=str(row["external_id"]),
        url=row["url"],
        title=row.get("title"),
        price_warm=row.get("price_warm"),
        price_cold=row.get("price_cold"),
        size_sqm=row.get("size_sqm"),
        rooms=row.get("rooms"),
        listing_type=ListingType(row.get("listing_type") or "unknown"),
        district=row.get("district"),
        address=row.get("address"),
        city=row.get("city"),
        available_from=_as_date(row.get("available_from")),
        available_to=_as_date(row.get("available_to")),
        fit_score=row.get("fit_score"),
        summary=row.get("summary"),
        raw=row.get("raw") or {},
    )


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

    # -- frontend reads ------------------------------------------------------
    def web_listings(self, limit: int = 200) -> list[dict]:
        """Raw listing rows (incl. status) for the dashboard, newest first."""
        resp = (
            self.client.table(TABLE)
            .select("*").order("first_seen_at", desc=True).limit(limit).execute()
        )
        return resp.data or []

    def set_status(self, source: str, external_id: str, status: str) -> None:
        now = datetime.now(UTC).isoformat()
        (
            self.client.table(TABLE)
            .update({"status": status, "status_updated_at": now})
            .eq("source", source).eq("external_id", external_id).execute()
        )

    def latest_run(self) -> dict | None:
        resp = (
            self.client.table(RUNS_TABLE)
            .select("*").order("created_at", desc=True).limit(1).execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None

    def all_listings(self, limit: int = 2000) -> list[Listing]:
        """Every stored listing (newest first), rebuilt as Listings — the wiki's stats corpus."""
        resp = (
            self.client.table(TABLE)
            .select("*")
            .order("first_seen_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [row_to_listing(r) for r in (resp.data or [])]

    def record_run(self, result: RunResult) -> None:
        """Persist one run's metrics to the `runs` table (best-effort; caller logs failures)."""
        self.client.table(RUNS_TABLE).insert(run_to_row(result)).execute()

    # -- human-in-the-loop feedback -----------------------------------------
    def record_notification(self, message_id: int, source: str, external_id: str) -> None:
        """Map a sent Telegram message to its listing so reactions can be resolved later."""
        self.client.table("notifications").upsert(
            {"message_id": message_id, "source": source, "external_id": external_id},
            on_conflict="message_id",
        ).execute()

    def listing_for_message(self, message_id: int) -> tuple[str, str] | None:
        resp = (
            self.client.table("notifications")
            .select("source, external_id").eq("message_id", message_id).limit(1).execute()
        )
        rows = resp.data or []
        return (rows[0]["source"], rows[0]["external_id"]) if rows else None

    def save_feedback(self, source: str, external_id: str, reaction) -> None:
        self.client.table("feedback").insert({
            "source": source, "external_id": external_id,
            "sentiment": reaction.sentiment, "emoji": reaction.emoji,
            "update_id": reaction.update_id,
        }).execute()

    def get_state(self, key: str, default: str = "") -> str:
        resp = self.client.table("bot_state").select("value").eq("key", key).limit(1).execute()
        rows = resp.data or []
        return rows[0]["value"] if rows else default

    def set_state(self, key: str, value: str) -> None:
        self.client.table("bot_state").upsert(
            {"key": key, "value": value}, on_conflict="key"
        ).execute()

    def preference_signal(self):
        """Aggregate stored feedback into a PreferenceSignal, keyed by the listing's district."""
        from apartment_agent.feedback import summarize_by_district

        fb = (self.client.table("feedback").select("source, external_id, sentiment").execute().data
              or [])
        if not fb:
            return summarize_by_district([])
        # resolve each reaction's district via the listing row
        districts: dict[tuple[str, str], str] = {}
        for source in {f["source"] for f in fb}:
            ids = [f["external_id"] for f in fb if f["source"] == source]
            rows = (
                self.client.table(TABLE).select("external_id, district, city")
                .eq("source", source).in_("external_id", ids).execute().data or []
            )
            for r in rows:
                districts[(source, r["external_id"])] = r.get("district") or r.get("city") or ""
        pairs = [
            (districts.get((f["source"], f["external_id"]), ""), int(f["sentiment"])) for f in fb
        ]
        return summarize_by_district(pairs)

    def mark_notified(self, source: str, external_ids: list[str]) -> None:
        if not external_ids:
            return
        now = datetime.now(UTC).isoformat()
        (
            self.client.table(TABLE)
            .update({"notified_at": now})
            .eq("source", source)
            .in_("external_id", external_ids)
            .execute()
        )
