"""Background agent runner for the dashboard.

A single agent run can take a while (scraping, detail fetches, LLM). The 'Search now' button and the
auto-search timer trigger a run in a background thread and return immediately; the frontend polls
status. Only one run executes at a time.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

log = logging.getLogger(__name__)


class AgentRunner:
    """Runs the agent pipeline off the request thread, tracking running/last-finished state.

    `run_fn` defaults to the real pipeline (`main.run_pipeline`) but is injectable for tests.
    """

    def __init__(self, settings, run_fn=None):
        self.settings = settings
        self._run_fn = run_fn
        self._lock = threading.Lock()
        self._running = False
        self._started_at: datetime | None = None
        self._last_finished_at: datetime | None = None
        self._last_error: str | None = None

    @property
    def running(self) -> bool:
        return self._running

    def state(self) -> dict:
        return {
            "running": self._running,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "last_finished_at": (
                self._last_finished_at.isoformat() if self._last_finished_at else None
            ),
            "last_error": self._last_error,
        }

    def trigger(self) -> bool:
        """Start a run in the background. Returns False if one is already in flight."""
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._started_at = datetime.now(UTC)
            self._last_error = None
        threading.Thread(target=self._run, name="agent-run", daemon=True).start()
        return True

    def _run(self) -> None:
        try:
            run_fn = self._run_fn
            if run_fn is None:
                from apartment_agent.main import run_pipeline

                run_fn = run_pipeline
            result = run_fn(self.settings)
            log.info("web-triggered run done: new=%s matched=%s",
                     getattr(result, "new", "?"), getattr(result, "matched", "?"))
        except Exception as e:  # noqa: BLE001 - surface to the dashboard, don't crash the thread
            self._last_error = str(e)
            log.exception("web-triggered run failed")
        finally:
            with self._lock:
                self._running = False
                self._last_finished_at = datetime.now(UTC)
