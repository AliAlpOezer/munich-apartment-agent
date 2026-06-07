"""Web dashboard tests — store helpers + API via TestClient (in-memory store, fake runner)."""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from apartment_agent.web.app import create_app
from apartment_agent.web.runner import AgentRunner
from apartment_agent.web.store import (
    InMemoryStore,
    listing_key,
    order_cards,
    parse_key,
    report_text,
    to_card,
)


def _row(ext_id, status="new", fit=None, **kw):
    base = dict(source="wg_gesucht", external_id=ext_id, url=f"http://x/{ext_id}",
                title=f"L{ext_id}", price_warm=650, size_sqm=18, listing_type="wg_room",
                district="Schwabing", status=status, fit_score=fit,
                first_seen_at=f"2026-06-0{ext_id}T10:00:00+00:00")
    base.update(kw)
    return base


# --- pure helpers ----------------------------------------------------------
def test_key_roundtrip():
    assert parse_key(listing_key("wg_gesucht", "123")) == ("wg_gesucht", "123")


def test_to_card_marks_new():
    assert to_card(_row("1", status="new"))["is_new"] is True
    assert to_card(_row("2", status="seen"))["is_new"] is False


def test_order_cards_new_first_then_fit():
    cards = [to_card(r) for r in [
        _row("1", status="seen", fit=90),
        _row("2", status="new", fit=50),
        _row("3", status="new", fit=80),
        _row("4", status="sent", fit=99),
    ]]
    order = [c["key"] for c in order_cards(cards)]
    # new (sorted by fit desc) come first, then seen, then sent
    assert order == ["wg_gesucht:3", "wg_gesucht:2", "wg_gesucht:1", "wg_gesucht:4"]


def test_report_text_variants():
    assert report_text(None) == "No runs yet."
    assert report_text({"new": 3, "matched": 5}) == "Found 3 new listing(s)."
    assert report_text({"new": 0, "matched": 4}) == "No new listings — 4 already-seen match(es)."
    assert report_text({"new": 0, "matched": 0}) == "Nothing matched this search."


# --- API -------------------------------------------------------------------
@pytest.fixture
def client():
    store = InMemoryStore(
        rows=[_row("1", status="new", fit=70), _row("2", status="seen", fit=80)],
        last_run={"new": 1, "matched": 2, "finished_at": "2026-06-07T09:00:00+00:00"},
    )
    runner = AgentRunner(settings=None, run_fn=lambda s: None)
    app = create_app(store, runner, auto_search_minutes=30)
    return TestClient(app), store


def test_list_listings_ordered(client):
    c, _ = client
    keys = [x["key"] for x in c.get("/api/listings").json()["listings"]]
    assert keys == ["wg_gesucht:1", "wg_gesucht:2"]  # new before seen


def test_update_status_ok_and_persists(client):
    c, _ = client
    r = c.post("/api/listings/status", json={"key": "wg_gesucht:1", "status": "sent"})
    assert r.status_code == 200 and r.json()["status"] == "sent"
    card = next(x for x in c.get("/api/listings").json()["listings"] if x["key"] == "wg_gesucht:1")
    assert card["status"] == "sent"


def test_update_status_validation(client):
    c, _ = client
    bad = c.post("/api/listings/status", json={"key": "wg_gesucht:1", "status": "bad"})
    missing = c.post("/api/listings/status", json={"key": "nope:9", "status": "seen"})
    assert bad.status_code == 400 and missing.status_code == 404


def test_status_endpoint_reports_run(client):
    c, _ = client
    body = c.get("/api/status").json()
    assert body["report"] == "Found 1 new listing(s)."
    assert body["auto_search_minutes"] == 30
    assert body["last_activity"] == "2026-06-07T09:00:00+00:00"
    assert body["agent"]["running"] is False


def test_search_triggers_and_conflicts_when_running():
    store = InMemoryStore()
    release = threading.Event()
    started = threading.Event()

    def slow(_settings):
        started.set()
        release.wait(2)

    runner = AgentRunner(settings=None, run_fn=slow)
    c = TestClient(create_app(store, runner))
    try:
        assert c.post("/api/search").json()["started"] is True
        assert started.wait(1)
        assert c.post("/api/search").status_code == 409   # already running
    finally:
        release.set()
