"""Observability tests: per-node timings, token tracking, and the runs-row mapping."""

from __future__ import annotations

from datetime import UTC, datetime

from apartment_agent.config import Settings
from apartment_agent.db.supabase_client import run_to_row
from apartment_agent.graph import Deps, build_graph
from apartment_agent.llm.router import ModelRouter, Tier
from apartment_agent.models import RunResult
from tests.test_graph import StubSource, _listing
from tests.test_router import _settings


def test_node_timings_recorded_for_every_executed_node():
    adapter = StubSource([_listing("a", 650.0)], warm_by_id={"a": 680.0})
    s = Settings(dry_run=True, enable_llm_enrich=False, enable_wiki=False)
    deps = Deps(settings=s, filter_cfg=s.filter_config(), adapters=[adapter])
    final = build_graph(deps).invoke({"result": RunResult()})
    timings = final["result"].node_timings_ms
    # nodes that run on a dry-run with one matching listing
    assert {"scrape", "filter", "dedup", "detail"} <= set(timings)
    assert all(v >= 0 for v in timings.values())


class _UsageModel:
    def invoke(self, _messages):
        return type("R", (), {"content": "ok", "usage_metadata": {
            "input_tokens": 10, "output_tokens": 5,
        }})()


def test_router_accumulates_token_usage(monkeypatch):
    r = ModelRouter(_settings())
    monkeypatch.setattr(r, "_make", lambda provider, model_id: _UsageModel())
    r.complete("s", "u", tier=Tier.CHEAP, max_tier=Tier.CHEAP)
    r.complete("s", "u", tier=Tier.CHEAP, max_tier=Tier.CHEAP)
    assert r.usage == {"calls": 2, "input_tokens": 20, "output_tokens": 10}


def test_run_to_row_maps_metrics():
    r = RunResult(
        scraped=10, matched=4, new=2, notified=1, errors=["boom"],
        started_at=datetime(2026, 6, 6, 10, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 6, 6, 10, 0, 5, tzinfo=UTC),
        node_timings_ms={"scrape": 12.0},
        tokens={"calls": 3, "input_tokens": 100, "output_tokens": 40},
    )
    row = run_to_row(r)
    assert row["scraped"] == 10 and row["new"] == 2
    assert row["errors"] == 1 and row["error_detail"] == ["boom"]   # count + detail
    assert row["duration_ms"] == 5000.0
    assert row["tokens"]["input_tokens"] == 100
    assert row["node_timings_ms"] == {"scrape": 12.0}
