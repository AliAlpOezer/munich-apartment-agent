---
type: decision
title: Web dashboard architecture (single-flight lock, header-token auth, vanilla-JS + polling)
description: Three coupled choices that keep the dashboard tiny — one run at a time via a lock, auth via a header token, and a build-free polling frontend.
resource: src/apartment_agent/web/
tags: [decision, web, fastapi, auth, spa]
timestamp: 2026-07-12T00:00:00Z
---

## Context

The dashboard exists to view listings and trigger a search by hand. It should be dependable and cheap to run, not a full web app. Three sub-choices define it.

## What we chose

1. **Single-flight run lock** — at most one pipeline run at a time.
2. **Header-token auth** — an optional `X-API-Token` header.
3. **Vanilla-JS SPA + polling** — no framework, no build step, poll every ~4s.

## How it works (beginner-first)

- **Lock**: `AgentRunner` guards runs with a `threading.Lock` + `_running` flag and runs `run_pipeline` on a daemon thread. `POST /api/search` returns HTTP **409** if a run is already in flight, so a double-click can't start two runs.
- **Auth**: if `web_api_token` is set, requests must send it in `X-API-Token`. The token lives in browser `localStorage` and is **never embedded in the served HTML**, so viewing source doesn't leak it.
- **Frontend**: hand-written HTML/CSS/JS in `static/` polls `/api/listings` and `/api/status` every ~4s and shows an auto-search countdown. See the [web dashboard component](../components/web-dashboard.md).

## Alternatives & trade-offs

- **A job queue instead of a single-flight lock**: could accept and serialize many run requests. **Trade-off**: a queue, worker, and state to manage — for one user who triggers the occasional manual run, a lock + 409 is enough. WORSE at: a rejected 409 is lost, not queued, so the user must click again.
- **Cookie/session auth instead of a header token**: standard browser login, CSRF-protected. **Trade-off**: session store, login flow, cookie handling. A header token is a one-liner. WORSE at: a static token is coarse (no per-user sessions, no easy rotation/expiry).
- **A framework + WebSockets instead of vanilla-JS + polling**: instant push updates, richer UI, component ergonomics. **Trade-off**: a build toolchain, dependencies, and a WebSocket server. WORSE at: ~4s polling has latency and makes redundant requests, where WebSockets would be instant and lighter on the wire.

## Why this serves the goal

Each choice picks the smallest thing that works for a single-user, single-box tool: minimal dependencies, no build step, and no way to accidentally start concurrent runs.

## Revisit when

- Multiple users need real accounts/sessions (move to cookie auth).
- Concurrent or queued runs become a real need (add a queue).
- Real-time UX matters enough to justify a framework + WebSockets.

## Related pages

- Component: [web dashboard](../components/web-dashboard.md)
- Ops caveat: [current state](../state/current-state.md) (broken HTTPS URL)
