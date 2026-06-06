"""Tests for the eval harness — offline against fake routers, plus an opt-in live run."""

from __future__ import annotations

import json
import os
import re

import pytest

from apartment_agent.config import load_settings
from apartment_agent.evals import GOLDEN, judge_synthesis, run_fit_evals


class _ScoringRouter:
    """Free-model stand-in: structured output unsupported, completion returns a scored JSON."""

    def __init__(self, scores: dict[str, int]):
        self.scores = scores

    def structured(self, *a, **k):
        raise RuntimeError("no tool calling")

    def complete(self, system, user, **k):
        ext = re.search(r"wg-gesucht\.de/(\w+)", user).group(1)
        return json.dumps({"fit_score": self.scores[ext], "summary": "x", "confidence": 0.9})


def test_fit_evals_all_in_band_pass():
    # scores chosen to sit inside each golden band
    router = _ScoringRouter({"g1": 85, "g2": 70, "g3": 60, "g4": 30})
    report = run_fit_evals(router)
    assert report.total == len(GOLDEN)
    assert report.pass_rate == 1.0 and all(r.passed for r in report.results)


def test_fit_evals_detect_misranking():
    # g1 is the ideal match but scored 5 -> must fail its band; g4 over-scored -> fail
    router = _ScoringRouter({"g1": 5, "g2": 70, "g3": 60, "g4": 95})
    report = run_fit_evals(router)
    failed = {r.name for r in report.results if not r.passed}
    assert failed == {"ideal-central-cheap", "poor-tiny-and-at-cap"}
    assert report.pass_rate < 1.0


class _ReplyRouter:
    def __init__(self, reply: str):
        self.reply = reply

    def complete(self, system, user, **k):
        return self.reply


def test_judge_synthesis_parses_grounded_verdict():
    v = judge_synthesis(_ReplyRouter('{"grounded": true, "reason": "matches facts"}'),
                        facts="median 640", synthesis="Rents cluster around 640.")
    assert v.grounded and "matches" in v.reason


def test_judge_synthesis_flags_missing_json():
    v = judge_synthesis(_ReplyRouter("I think it is fine"), facts="x", synthesis="y")
    assert not v.grounded


# --- opt-in live run (network): RUN_LIVE_EVALS=1 pytest -k live ---
@pytest.mark.skipif(os.environ.get("RUN_LIVE_EVALS") != "1", reason="set RUN_LIVE_EVALS=1 to run")
def test_live_fit_evals():
    s = load_settings()
    if not (s.opencode_zen_api_key or s.openrouter_api_key or s.anthropic_api_key):
        pytest.skip("no LLM keys configured")
    from apartment_agent.llm.router import ModelRouter

    report = run_fit_evals(ModelRouter(s))
    # free tiers are noisy (and over-score marginal listings) — just assert the harness ran end to
    # end and at least scored the clearly-ideal case in band. Use the printed report to tune models.
    print(f"live fit evals: {report.passed}/{report.total} in band")
    ideal = next(r for r in report.results if r.name == "ideal-central-cheap")
    assert ideal.passed
