"""FastAPI app: dashboard API + static frontend.

`create_app(store, runner, settings)` is injectable so tests pass an in-memory store and a fake
runner. `default_app()` wires the real Supabase-backed store and the real pipeline runner.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from apartment_agent.web.runner import AgentRunner
from apartment_agent.web.store import STATUSES, Store, report_text

log = logging.getLogger(__name__)

_STATIC = Path(__file__).parent / "static"


class StatusUpdate(BaseModel):
    key: str
    status: str


def create_app(store: Store, runner: AgentRunner, *, auto_search_minutes: int = 0) -> FastAPI:
    app = FastAPI(title="Munich Apartment Agent", docs_url="/api/docs")

    @app.get("/api/listings")
    def list_listings() -> dict:
        return {"listings": store.listings()}

    @app.post("/api/listings/status")
    def update_status(body: StatusUpdate) -> dict:
        if body.status not in STATUSES:
            raise HTTPException(400, f"status must be one of {STATUSES}")
        if not store.set_status(body.key, body.status):
            raise HTTPException(404, "listing not found")
        return {"ok": True, "key": body.key, "status": body.status}

    @app.get("/api/status")
    def status() -> dict:
        run = store.last_run()
        last_activity = None
        if run:
            last_activity = run.get("finished_at") or run.get("created_at")
        return {
            "agent": runner.state(),
            "last_run": run,
            "report": report_text(run),
            "last_activity": last_activity,
            "auto_search_minutes": auto_search_minutes,
        }

    @app.post("/api/search")
    def search() -> dict:
        if not runner.trigger():
            raise HTTPException(409, "a search is already running")
        return {"started": True}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_STATIC / "index.html")

    if _STATIC.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    return app


def default_app() -> FastAPI:
    """The real app, wired from environment settings (Supabase + live pipeline)."""
    from apartment_agent.config import load_settings
    from apartment_agent.db.supabase_client import ListingsDB
    from apartment_agent.web.store import SupabaseStore

    settings = load_settings()
    if not (settings.supabase_url and settings.supabase_service_key):
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY required to serve the dashboard")
    db = ListingsDB(settings.supabase_url, settings.supabase_service_key)
    store = SupabaseStore(db)
    runner = AgentRunner(settings)
    return create_app(store, runner, auto_search_minutes=settings.web_auto_search_minutes)
