"""Local SQLite access for listings: dedup lookups, upsert, notify marking, runs, feedback.

Drop-in replacement for the former Supabase client — same public `ListingsDB` API — backed by a
single local SQLite file. The schema self-initializes on first connect (no server, no manual apply
step), which is the whole point of moving off Supabase: less to run, less to break. Columns that
were Postgres `jsonb` (raw / tokens / node_timings_ms / error_detail) are stored as TEXT JSON.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import UTC, date, datetime

from apartment_agent.models import Listing, ListingType, RunResult

log = logging.getLogger(__name__)

TABLE = "listings"
RUNS_TABLE = "runs"

# SQLite DDL. Timestamps are ISO-8601 TEXT (UTC); dates are ISO TEXT. Mirrors the old Postgres
# schema field-for-field so the rest of the app is untouched.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source            TEXT    NOT NULL,
    external_id       TEXT    NOT NULL,
    url               TEXT    NOT NULL,
    title             TEXT,
    price_warm        REAL,
    price_cold        REAL,
    size_sqm          REAL,
    rooms             REAL,
    listing_type      TEXT    NOT NULL DEFAULT 'unknown',
    district          TEXT,
    address           TEXT,
    city              TEXT,
    available_from    TEXT,
    available_to      TEXT,
    posted_at         TEXT,
    fit_score         INTEGER,
    summary           TEXT,
    raw               TEXT    NOT NULL DEFAULT '{}',
    first_seen_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    notified_at       TEXT,
    status            TEXT    NOT NULL DEFAULT 'new',
    status_updated_at TEXT,
    UNIQUE (source, external_id)
);
CREATE INDEX IF NOT EXISTS listings_first_seen_idx ON listings (first_seen_at DESC);
CREATE INDEX IF NOT EXISTS listings_fit_idx        ON listings (fit_score DESC);
CREATE INDEX IF NOT EXISTS listings_status_idx     ON listings (status);

CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT,
    finished_at     TEXT,
    duration_ms     REAL,
    scraped         INTEGER,
    matched         INTEGER,
    new             INTEGER,
    notified        INTEGER,
    errors          INTEGER,
    tokens          TEXT    NOT NULL DEFAULT '{}',
    node_timings_ms TEXT    NOT NULL DEFAULT '{}',
    error_detail    TEXT    NOT NULL DEFAULT '[]',
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS runs_created_idx ON runs (created_at DESC);

CREATE TABLE IF NOT EXISTS notifications (
    message_id  INTEGER PRIMARY KEY,
    source      TEXT    NOT NULL,
    external_id TEXT    NOT NULL,
    sent_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,
    external_id TEXT    NOT NULL,
    sentiment   INTEGER NOT NULL,
    emoji       TEXT,
    update_id   INTEGER,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS feedback_listing_idx ON feedback (source, external_id);

CREATE TABLE IF NOT EXISTS bot_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Columns written on upsert. Excludes server-managed columns (id, first_seen_at) and user-workflow
# columns (status, status_updated_at, notified_at) so a re-scrape refreshes the listing data without
# clobbering "seen"/"notified" state the user or a prior run set.
_UPSERT_COLS = (
    "source", "external_id", "url", "title", "price_warm", "price_cold", "size_sqm", "rooms",
    "listing_type", "district", "address", "city", "available_from", "available_to", "posted_at",
    "fit_score", "summary", "raw",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _as_date(value) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) and value else None


def run_to_row(r: RunResult) -> dict:
    """Map a RunResult to a `runs` row. tokens/node_timings_ms/error_detail stay native here (the
    caller JSON-encodes them for storage); kept native so observability code reads them directly."""
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


def row_to_listing(row: dict) -> Listing:
    """Inverse of `listing_to_row` — rebuild a Listing from a stored row (for the wiki corpus)."""
    raw = row.get("raw")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = {}
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
        raw=raw or {},
    )


def listing_to_row(listing: Listing) -> dict:
    """Map a Listing to a `listings` row (JSON-serializable; `raw` is a JSON string for SQLite)."""
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
        "raw": json.dumps(listing.raw or {}),
    }


class ListingsDB:
    """SQLite-backed store. Opens a short-lived connection per operation (WAL mode), so it is safe
    to call from the web request threads and the background pipeline thread without shared state."""

    def __init__(self, db_path: str = "apartments.sqlite"):
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(parent, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # -- dedup / persistence -------------------------------------------------
    def existing_external_ids(self, source: str, external_ids: list[str]) -> set[str]:
        """Which of these external_ids are already stored for the source."""
        if not external_ids:
            return set()
        marks = ",".join("?" * len(external_ids))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT external_id FROM {TABLE} WHERE source = ? AND external_id IN ({marks})",
                [source, *external_ids],
            ).fetchall()
        return {str(r["external_id"]) for r in rows}

    def upsert_listings(self, listings: list[Listing]) -> int:
        if not listings:
            return 0
        cols = ", ".join(_UPSERT_COLS)
        marks = ", ".join("?" * len(_UPSERT_COLS))
        # On conflict, refresh the scraped/enriched fields but keep source+external_id (the key).
        updates = ", ".join(
            f"{c} = excluded.{c}" for c in _UPSERT_COLS if c not in ("source", "external_id")
        )
        sql = (
            f"INSERT INTO {TABLE} ({cols}) VALUES ({marks}) "
            f"ON CONFLICT(source, external_id) DO UPDATE SET {updates}"
        )
        with self._conn() as conn:
            conn.executemany(
                sql, [[listing_to_row(x)[c] for c in _UPSERT_COLS] for x in listings]
            )
            conn.commit()
        return len(listings)

    def mark_notified(self, source: str, external_ids: list[str]) -> None:
        if not external_ids:
            return
        marks = ",".join("?" * len(external_ids))
        with self._conn() as conn:
            conn.execute(
                f"UPDATE {TABLE} SET notified_at = ? "
                f"WHERE source = ? AND external_id IN ({marks})",
                [_now(), source, *external_ids],
            )
            conn.commit()

    # -- frontend reads ------------------------------------------------------
    def web_listings(self, limit: int = 200) -> list[dict]:
        """Raw listing rows (incl. status) for the dashboard, newest first."""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {TABLE} ORDER BY first_seen_at DESC LIMIT ?", [limit]
            ).fetchall()
        return [dict(r) for r in rows]

    def set_status(self, source: str, external_id: str, status: str) -> None:
        with self._conn() as conn:
            conn.execute(
                f"UPDATE {TABLE} SET status = ?, status_updated_at = ? "
                f"WHERE source = ? AND external_id = ?",
                [status, _now(), source, external_id],
            )
            conn.commit()

    def all_listings(self, limit: int = 2000) -> list[Listing]:
        """Every stored listing (newest first), rebuilt as Listings — the wiki's stats corpus."""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {TABLE} ORDER BY first_seen_at DESC LIMIT ?", [limit]
            ).fetchall()
        return [row_to_listing(dict(r)) for r in rows]

    # -- runs / observability ------------------------------------------------
    def latest_run(self) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {RUNS_TABLE} ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        out = dict(row)
        for k in ("tokens", "node_timings_ms", "error_detail"):  # decode jsonb-equivalent columns
            if isinstance(out.get(k), str):
                try:
                    out[k] = json.loads(out[k])
                except (ValueError, TypeError):
                    pass
        return out

    def record_run(self, result: RunResult) -> None:
        """Persist one run's metrics to the `runs` table (JSON-encoding the structured columns)."""
        row = run_to_row(result)
        for k in ("tokens", "node_timings_ms", "error_detail"):
            row[k] = json.dumps(row[k])
        cols = ", ".join(row)
        marks = ", ".join("?" * len(row))
        with self._conn() as conn:
            conn.execute(
                f"INSERT INTO {RUNS_TABLE} ({cols}) VALUES ({marks})", list(row.values())
            )
            conn.commit()

    # -- human-in-the-loop feedback -----------------------------------------
    def record_notification(self, message_id: int, source: str, external_id: str) -> None:
        """Map a sent Telegram message to its listing so reactions can be resolved later."""
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO notifications (message_id, source, external_id) VALUES (?, ?, ?) "
                "ON CONFLICT(message_id) DO UPDATE SET source = excluded.source, "
                "external_id = excluded.external_id",
                [message_id, source, external_id],
            )
            conn.commit()

    def listing_for_message(self, message_id: int) -> tuple[str, str] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT source, external_id FROM notifications WHERE message_id = ? LIMIT 1",
                [message_id],
            ).fetchone()
        return (row["source"], str(row["external_id"])) if row else None

    def save_feedback(self, source: str, external_id: str, reaction) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO feedback (source, external_id, sentiment, emoji, update_id) "
                "VALUES (?, ?, ?, ?, ?)",
                [source, external_id, reaction.sentiment, reaction.emoji, reaction.update_id],
            )
            conn.commit()

    def get_state(self, key: str, default: str = "") -> str:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM bot_state WHERE key = ? LIMIT 1", [key]
            ).fetchone()
        return row["value"] if row else default

    def set_state(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO bot_state (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                [key, value],
            )
            conn.commit()

    def preference_signal(self):
        """Aggregate stored feedback into a PreferenceSignal, keyed by the listing's district."""
        from apartment_agent.feedback import summarize_by_district

        with self._conn() as conn:
            rows = conn.execute(
                "SELECT COALESCE(NULLIF(l.district, ''), NULLIF(l.city, ''), '') AS district, "
                "       f.sentiment AS sentiment "
                "FROM feedback f "
                "LEFT JOIN listings l ON l.source = f.source AND l.external_id = f.external_id"
            ).fetchall()
        pairs = [(r["district"] or "", int(r["sentiment"])) for r in rows]
        return summarize_by_district(pairs)
