"""Router tests: confidence-driven escalation (was C2), structured output, and the enrich fallback.

No network: `_make` is monkeypatched to return scripted fake chat models.
"""

from __future__ import annotations

from datetime import date

import pytest

from apartment_agent.config import Settings
from apartment_agent.graph import Assessment, _parse_assessment, assess_listing
from apartment_agent.llm.router import ModelRouter, Tier
from apartment_agent.models import Listing, ListingType


def _settings() -> Settings:
    # tiers resolve to candidates: opencode/c1 (cheap) -> opencode/m1 (medium) -> opencode/h1 (hard)
    return Settings(opencode_zen_api_key="x", tier1_models="c1", tier2_model="m1", tier3_model="h1")


class _TextModel:
    def __init__(self, content):
        self._content = content

    def invoke(self, _messages):
        return type("R", (), {"content": self._content})()


class _StructModel:
    def __init__(self, result):
        self._result = result

    def with_structured_output(self, _schema):
        return self

    def invoke(self, _messages):
        return self._result


def _router(monkeypatch, by_model):
    r = ModelRouter(_settings())
    monkeypatch.setattr(r, "_make", lambda provider, model_id: by_model[model_id])
    return r


# --- complete() escalation ---
def test_complete_escalates_until_accepted(monkeypatch):
    r = _router(monkeypatch, {
        "c1": _TextModel("BAD"), "m1": _TextModel("BAD"), "h1": _TextModel("GOOD"),
    })
    out = r.complete("s", "u", tier=Tier.CHEAP, max_tier=Tier.HARD, accept=lambda c: c == "GOOD")
    assert out == "GOOD"


def test_complete_returns_last_when_none_accepted(monkeypatch):
    r = _router(monkeypatch, {
        "c1": _TextModel("a"), "m1": _TextModel("b"), "h1": _TextModel("c"),
    })
    out = r.complete("s", "u", tier=Tier.CHEAP, max_tier=Tier.HARD, accept=lambda c: False)
    assert out == "c"  # best-effort: the last successful result


def test_complete_no_accept_returns_first(monkeypatch):
    r = _router(monkeypatch, {
        "c1": _TextModel("first"), "m1": _TextModel("x"), "h1": _TextModel("y"),
    })
    assert r.complete("s", "u", tier=Tier.CHEAP, max_tier=Tier.HARD) == "first"


# --- structured() escalation on confidence ---
def test_structured_escalates_on_low_confidence(monkeypatch):
    r = _router(monkeypatch, {
        "c1": _StructModel(Assessment(fit_score=50, summary="meh", confidence=0.2)),
        "m1": _StructModel(Assessment(fit_score=80, summary="good", confidence=0.9)),
        "h1": _StructModel(Assessment(fit_score=0, summary="unused", confidence=1.0)),
    })
    out = r.structured("s", "u", Assessment, tier=Tier.CHEAP, max_tier=Tier.HARD,
                       accept=lambda a: (a.confidence or 0) >= 0.5)
    assert out.fit_score == 80 and out.confidence == 0.9


# --- parsing ---
def test_parse_assessment_with_confidence():
    a = _parse_assessment('{"fit_score": 88, "summary": "great", "confidence": 0.7}')
    assert a.fit_score == 88 and a.summary == "great" and a.confidence == 0.7


def test_parse_assessment_clamps_and_tolerates_prose():
    a = _parse_assessment('thinking... {"fit_score": 150, "summary": "x"} done')
    assert a.fit_score == 100 and a.confidence is None


# --- assess_listing fallback path ---
def _listing() -> Listing:
    return Listing(source="wg_gesucht", external_id="1", url="http://x/1", title="Room",
                   price_warm=650, size_sqm=18, listing_type=ListingType.WG_ROOM,
                   district="Schwabing", available_from=date(2026, 10, 1))


def test_assess_listing_uses_structured_when_available(monkeypatch):
    r = _router(monkeypatch, {
        "c1": _StructModel(Assessment(fit_score=77, summary="ok", confidence=0.9)),
        "m1": _StructModel(Assessment(fit_score=0, summary="", confidence=1.0)),
        "h1": _StructModel(Assessment(fit_score=0, summary="", confidence=1.0)),
    })
    a = assess_listing(r, _listing())
    assert a.fit_score == 77 and a.summary == "ok"


def test_assess_listing_falls_back_to_text(monkeypatch):
    # structured output unsupported (raises) -> regex JSON path over plain completion
    def boom(*a, **k):
        raise RuntimeError("no tool calling")

    r = ModelRouter(_settings())
    monkeypatch.setattr(r, "structured", boom)
    reply = '{"fit_score": 64, "summary": "fallback", "confidence": 0.8}'
    monkeypatch.setattr(r, "complete", lambda *a, **k: reply)
    a = assess_listing(r, _listing())
    assert a.fit_score == 64 and a.summary == "fallback"
