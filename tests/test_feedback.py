"""Feedback tests: reaction parsing, aggregation, sync orchestration, learned-preferences render."""

from __future__ import annotations

from datetime import date

from apartment_agent.feedback import (
    parse_reactions,
    summarize_by_district,
    sync_feedback,
)
from apartment_agent.models import FilterConfig
from apartment_agent.wiki import pages

_UPDATES = [
    {"update_id": 10, "message_reaction": {"message_id": 100,
                                           "new_reaction": [{"type": "emoji", "emoji": "👍"}]}},
    {"update_id": 11, "message_reaction": {"message_id": 101,
                                           "new_reaction": [{"type": "emoji", "emoji": "👎"}]}},
    {"update_id": 12, "message_reaction": {"message_id": 102,
                                           "new_reaction": [{"type": "emoji", "emoji": "🎉"}]}},
    {"update_id": 13, "message": {"text": "hello"}},  # not a reaction
]


def test_parse_reactions_extracts_known_emojis_only():
    reactions = parse_reactions(_UPDATES)
    assert [(r.message_id, r.sentiment) for r in reactions] == [(100, 1), (101, -1)]
    assert reactions[0].update_id == 10 and reactions[0].emoji == "👍"


def test_summarize_by_district_nets_sentiment():
    signal = summarize_by_district([
        ("Schwabing", 1), ("Schwabing", 1), ("Haar", -1), ("Garching", 1), ("Garching", -1),
    ])
    assert signal.liked == {"Schwabing": 2}
    assert signal.disliked == {"Haar": -1}
    assert "Garching" not in signal.liked and "Garching" not in signal.disliked  # nets to 0
    assert signal.total_reactions == 5


def test_sync_feedback_maps_saves_and_advances_offset():
    saved: list[tuple] = []
    state = {"offset": 0}

    def resolve(message_id):
        return ("wg_gesucht", "a") if message_id == 100 else None  # 101 unresolved -> skipped

    n = sync_feedback(
        fetch_updates=lambda offset: _UPDATES,
        resolve_listing=resolve,
        save_feedback=lambda s, e, r: saved.append((s, e, r.sentiment)),
        offset_get=lambda: state["offset"],
        offset_set=lambda v: state.__setitem__("offset", v),
    )
    assert n == 1 and saved == [("wg_gesucht", "a", 1)]
    assert state["offset"] == 14  # max update_id (13) + 1, so updates aren't re-delivered


def test_sync_feedback_no_updates_is_noop():
    state = {"offset": 5}
    n = sync_feedback(
        fetch_updates=lambda offset: [],
        resolve_listing=lambda m: None,
        save_feedback=lambda *a: None,
        offset_get=lambda: state["offset"],
        offset_set=lambda v: state.__setitem__("offset", v),
    )
    assert n == 0 and state["offset"] == 5  # unchanged


def test_render_preferences_renders_learned_signal():
    signal = summarize_by_district([("Schwabing", 2), ("Haar", -1)])
    page = pages.render_preferences(FilterConfig(), updated=date(2026, 6, 6), signal=signal)
    assert "Learned from your reactions" in page
    assert "Schwabing" in page and "Haar" in page
    assert "no reactions yet" not in page


def test_render_preferences_placeholder_without_signal():
    page = pages.render_preferences(FilterConfig(), updated=date(2026, 6, 6))
    assert "no reactions yet" in page
