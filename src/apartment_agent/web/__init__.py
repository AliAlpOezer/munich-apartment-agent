"""Web dashboard for the apartment agent.

A small FastAPI app that renders the matched listings as cards, lets you mark each new / seen / sent,
shows the agent's last activity + run report, and can trigger a fresh search on demand or on a timer.
Reads/writes the same Supabase data the agent uses.

  store.py   - data access (Supabase-backed, plus an in-memory store for dev/tests) + pure helpers
  runner.py  - triggers an agent run in the background, tracks running/last-run state
  app.py     - FastAPI routes + static frontend (create_app is injectable for tests)
  static/    - the single-page frontend (vanilla JS, no build step)
"""

from __future__ import annotations

from apartment_agent.web.app import create_app

__all__ = ["create_app"]
