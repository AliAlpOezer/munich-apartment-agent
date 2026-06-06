"""Durable-execution tests: the pipeline runs under a checkpointer, and an interrupted run resumes.

Uses LangGraph's in-memory checkpointer so the tests need no SQLite file or network.
"""

from __future__ import annotations

from typing import TypedDict

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from apartment_agent.checkpoint import new_thread_id, resume_incomplete
from apartment_agent.config import Settings
from apartment_agent.graph import Deps, build_graph
from apartment_agent.models import RunResult
from tests.test_graph import StubSource, _listing


def test_thread_id_is_unique():
    assert new_thread_id() != new_thread_id()


def test_pipeline_runs_under_checkpointer_and_completes():
    adapter = StubSource([_listing("a", 650.0)], warm_by_id={"a": 680.0})
    s = Settings(dry_run=True, enable_llm_enrich=False, enable_wiki=False)
    deps = Deps(settings=s, filter_cfg=s.filter_config(), adapters=[adapter])
    graph = build_graph(deps, checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": new_thread_id()}}
    graph.invoke({"result": RunResult()}, config=cfg)
    # reached END => no pending next-nodes
    assert graph.get_state(cfg).next == ()


# --- resume semantics against real LangGraph ---
class _S(TypedDict, total=False):
    a: int
    b: int


def _build_flaky_graph(fail_state: dict):
    def n1(_s):
        return {"a": 1}

    def n2(_s):
        if fail_state["fail"]:
            fail_state["fail"] = False
            raise RuntimeError("boom")
        return {"b": 2}

    g = StateGraph(_S)
    g.add_node("n1", n1)
    g.add_node("n2", n2)
    g.add_edge(START, "n1")
    g.add_edge("n1", "n2")
    g.add_edge("n2", END)
    return g.compile(checkpointer=MemorySaver())


def test_resume_incomplete_finishes_an_interrupted_run():
    fail_state = {"fail": True}
    graph = _build_flaky_graph(fail_state)
    cfg = {"configurable": {"thread_id": "t1"}}

    with pytest.raises(Exception):  # noqa: B017 - n2 raises, leaving the run interrupted
        graph.invoke({}, config=cfg)
    assert graph.get_state(cfg).next == ("n2",)   # n1 done, n2 pending

    resumed = resume_incomplete(graph)
    assert "t1" in resumed
    snap = graph.get_state(cfg)
    assert snap.next == () and snap.values.get("b") == 2   # completed on resume


def test_resume_incomplete_noop_when_all_complete():
    graph = _build_flaky_graph({"fail": False})
    graph.invoke({}, config={"configurable": {"thread_id": "done"}})
    assert resume_incomplete(graph) == []
