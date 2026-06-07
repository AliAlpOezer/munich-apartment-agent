"""Data access for the dashboard, plus pure presentation helpers.

`Store` is the interface the API depends on; `SupabaseStore` is the production impl and
`InMemoryStore` backs dev/tests. The card serialization, ordering, and run-report wording are pure
functions so they are unit-tested without a database.
"""

from __future__ import annotations

from typing import Protocol

STATUSES = ("new", "seen", "sent")
_STATUS_RANK = {"new": 0, "seen": 1, "sent": 2}


def listing_key(source: str, external_id: str) -> str:
    return f"{source}:{external_id}"


def parse_key(key: str) -> tuple[str, str]:
    source, _, external_id = key.partition(":")
    return source, external_id


def to_card(row: dict) -> dict:
    """A DB listing row → the JSON card the frontend renders."""
    status = row.get("status") or "new"
    return {
        "key": listing_key(row["source"], str(row["external_id"])),
        "url": row.get("url"),
        "title": row.get("title") or "(no title)",
        "price_warm": row.get("price_warm"),
        "price_cold": row.get("price_cold"),
        "price_listed": row.get("price_listed"),
        "size_sqm": row.get("size_sqm"),
        "listing_type": row.get("listing_type") or "unknown",
        "district": row.get("district"),
        "city": row.get("city"),
        "available_from": row.get("available_from"),
        "fit_score": row.get("fit_score"),
        "summary": row.get("summary"),
        "status": status if status in STATUSES else "new",
        "first_seen_at": row.get("first_seen_at"),
        "is_new": status == "new",
    }


def order_cards(cards: list[dict]) -> list[dict]:
    """Stable ordering: status rank, then fit desc, then first_seen_at desc."""
    return sorted(
        cards,
        key=lambda c: (
            _STATUS_RANK.get(c["status"], 0),
            -(c["fit_score"] if c["fit_score"] is not None else -1),
            _neg_iso(c.get("first_seen_at")),
        ),
    )


def _neg_iso(value: str | None) -> str:
    # invert ISO timestamp ordering for "newest first" within a stable string sort
    if not value:
        return "~"  # sorts last
    return "".join(chr(255 - ord(ch)) if ch.isdigit() else ch for ch in value)


def report_text(run: dict | None) -> str:
    """Human summary of the last run for the dashboard banner."""
    if not run:
        return "No runs yet."
    new = run.get("new") or 0
    matched = run.get("matched") or 0
    if new > 0:
        return f"Found {new} new listing(s)."
    if matched > 0:
        return f"No new listings — {matched} already-seen match(es)."
    return "Nothing matched this search."


class Store(Protocol):
    def listings(self) -> list[dict]: ...
    def set_status(self, key: str, status: str) -> bool: ...
    def last_run(self) -> dict | None: ...


class InMemoryStore:
    """Dev/test store: holds listing rows and an optional last-run dict in memory."""

    def __init__(self, rows: list[dict] | None = None, last_run: dict | None = None):
        self._rows = {
            listing_key(r["source"], str(r["external_id"])): dict(r) for r in (rows or [])
        }
        self._last_run = last_run

    def listings(self) -> list[dict]:
        return order_cards([to_card(r) for r in self._rows.values()])

    def set_status(self, key: str, status: str) -> bool:
        if key not in self._rows or status not in STATUSES:
            return False
        self._rows[key]["status"] = status
        return True

    def last_run(self) -> dict | None:
        return self._last_run

    def set_last_run(self, run: dict | None) -> None:
        self._last_run = run


class SupabaseStore:
    """Production store backed by the agent's Supabase tables."""

    def __init__(self, db):
        self.db = db

    def listings(self) -> list[dict]:
        return order_cards([to_card(r) for r in self.db.web_listings()])

    def set_status(self, key: str, status: str) -> bool:
        if status not in STATUSES:
            return False
        source, external_id = parse_key(key)
        if not source or not external_id:
            return False
        self.db.set_status(source, external_id, status)
        return True

    def last_run(self) -> dict | None:
        return self.db.latest_run()
