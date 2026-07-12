---
type: component
title: Web dashboard (FastAPI + vanilla-JS SPA)
description: A small FastAPI backend and zero-build browser UI to view listings, trigger a search, and set listing status.
resource: src/apartment_agent/web/
tags: [component, web, fastapi, dashboard, spa]
timestamp: 2026-07-12T00:00:00Z
---

## What it does

Serves a single-page browser app that lists the matched apartments, lets you trigger a search on demand, and lets you mark a listing's status. **FastAPI** is a Python web framework (roughly Python's Express/Fastify). **SPA** = single-page app; here it is hand-written HTML/CSS/JS with no build step.

## Where it lives

`src/apartment_agent/web/`: `app.py` (routes), `runner.py` (`AgentRunner`), `store.py` (data access), `static/` (`index.html`, `app.js`, `config.js`, `style.css`).

## Interface

- `create_app(store, runner, auto_search_minutes, api_token, cors_origins)` — builds the FastAPI app.
- Routes:
  - `GET /api/listings` — the cards.
  - `POST /api/listings/status` — set a listing's status.
  - `GET /api/status` — run state / counters.
  - `POST /api/search` — trigger a run; returns **409** if a run is already in flight.
  - `GET /` — the static SPA.
- **Auth**: optional `X-API-Token` header. The token is kept in browser `localStorage` and **never embedded in the served page**. See [web dashboard architecture decision](../decisions/web-dashboard-architecture.md).
- `AgentRunner` — **single-flight** via a `threading.Lock` + `_running` flag; runs `run_pipeline` on a daemon thread so the HTTP request returns immediately.
- `store.py` — a `Store` **Protocol** (a structural interface) with `InMemoryStore` and `DbStore` implementations; `to_card` / `order_cards` order by status rank (`new < seen < sent`), then fit descending, then newest.

## Frontend behaviour

Polls `GET /api/listings` and `GET /api/status` every ~4 seconds and shows an auto-search countdown.

## Config / Settings keys that tune it

- `web_auto_search_minutes` (180) — the countdown / auto-trigger interval.
- `web_api_token` ("") — sets the required `X-API-Token`; empty disables auth.
- `web_cors_origins` ("*") — allowed CORS origins.

## Deployment note

Runs as the `apartment-dashboard.service` systemd unit (uvicorn on **port 8000**). Reachable on the tailnet at `http://alpiclawd.tail0f9474.ts.net:8000/`. The tidy HTTPS URL is currently **broken** — see [current state](../state/current-state.md).

## Related pages

- Decision: [web dashboard architecture](../decisions/web-dashboard-architecture.md)
- Uses: [database](database.md), [orchestration (`run_pipeline`)](orchestration.md)
- Ops: [current state](../state/current-state.md)
