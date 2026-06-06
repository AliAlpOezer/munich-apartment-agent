"""Durable execution helpers.

LangGraph persists the graph state after every super-step when compiled with a checkpointer, so a
crash mid-run (e.g. during the sequential `detail` fetches) resumes from the last completed node on
the next start instead of restarting the whole pipeline.

Each run gets a fresh thread id; before starting a new run we sweep for any *interrupted* prior
thread (one with pending next-nodes) and finish it first. The on-disk store is a SQLite file
(gitignored via `*.sqlite`).
"""

from __future__ import annotations

import logging
import uuid

log = logging.getLogger(__name__)


def new_thread_id() -> str:
    """A unique id for one pipeline run."""
    return f"run-{uuid.uuid4().hex[:12]}"


def _thread_ids(graph) -> list[str]:
    """Distinct thread ids known to the graph's checkpointer (most-recent first, de-duped)."""
    seen: set[str] = set()
    out: list[str] = []
    for ct in graph.checkpointer.list(None):
        tid = ct.config.get("configurable", {}).get("thread_id")
        if tid and tid not in seen:
            seen.add(tid)
            out.append(tid)
    return out


def resume_incomplete(graph, *, limit: int = 20) -> list[str]:
    """Finish any prior runs that were interrupted mid-pipeline.

    A thread whose latest state has pending `next` nodes never reached END — resume it by invoking
    with `None`, which continues from the last checkpoint. Returns the thread ids that were resumed.
    """
    resumed: list[str] = []
    for tid in _thread_ids(graph)[:limit]:
        config = {"configurable": {"thread_id": tid}}
        try:
            snapshot = graph.get_state(config)
        except Exception as e:  # noqa: BLE001 - a corrupt/old thread shouldn't block the new run
            log.warning("could not read checkpoint for %s: %s", tid, e)
            continue
        if snapshot.next:  # pending nodes => interrupted
            log.info("resuming interrupted run %s (pending: %s)", tid, snapshot.next)
            try:
                graph.invoke(None, config=config)
                resumed.append(tid)
            except Exception as e:  # noqa: BLE001 - resume failure is logged, not fatal
                log.warning("resume of %s failed: %s", tid, e)
    return resumed
