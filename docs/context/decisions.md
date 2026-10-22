# Decisions — munich-apartment-agent

One entry per settled decision, drawn from `docs/wiki/decisions/` (full rationale there if needed,
but this file is self-contained). Newest first.

### One Cloudflare Worker (cron + Queues + D1 + static dashboard) replaces the box (2026-10-22)
Status: settled · revisit-if WG-Gesucht blocks Cloudflare egress, or free-plan CPU limits (error
1102) bite.
User asked for Cloudflare hosting and no server. Python can't run there (curl-cffi, selectolax and
LangGraph's serializer are native; no Pyodide builds), Pages Functions have no cron, and the free
plan allows 10 ms CPU per invocation, so the run is split into queue jobs (one search page or one
detail page each) at concurrency 1. Rejected: Python on GitHub Actions cron + Pages UI (late, flaky
cron, two platforms), LangGraph.js (the queue already gives durable stages and retry), KV/Durable
Objects (no uniqueness constraint), Workers Paid (not needed yet). Telegram dropped: user chose
dashboard-only. Rationale: `docs/wiki/decisions/cloudflare-workers-hosting.md`.

### Filter on routed e-bike minutes to TUM and SAP Garching, not a radius (2026-10-22)
Status: settled · revisit-if anchors change or the user switches bike type (`BIKE_SPEED_KMH`).
Each listing's coordinates (from the search page's map markers) are routed with Valhalla
(`costing: bicycle`, 22 km/h); the slower anchor must be <= 30 min. Router failure -> flagged
haversine x 1.3 estimate, never a drop. The WG-Gesucht radius is derived as a guaranteed superset.
Supersedes the 5 km Alte Heide radius. Rationale: `docs/wiki/decisions/bike-time-filter.md`.

### Local SQLite instead of Supabase / managed Postgres
Status: superseded 2026-10-22 by D1 (hosting moved to Cloudflare); the SQL model carried over.
Chose a single local SQLite file (`ListingsDB`, self-initializing, WAL mode, short-lived connections
per op) over hosted Postgres because the agent runs on one small box with one writer — a network
dependency and credentials were pure overhead. Supabase was removed.
Cost accepted: no managed backups, no built-in remote access (must SSH to the box to see data).

### Free-first tiered LLM routing with confidence-driven escalation
Status: settled · revisit-if free tiers get so rate-limited that escalation dominates, or tier-1
quality fails evals.
Chose a 3-tier router (free OpenRouter → OpenCode Zen → Claude) that escalates only on error or an
answer below `confidence >= 0.5`, over always-Claude (simple but costs money every run forever) or a
single free model (free but brittle with no recovery). Cost scales with difficulty, not volume.
Cost accepted: variable, occasionally high latency — a hard listing can traverse several throttled
free models before reaching Claude.

### TLS-impersonation scraping (curl-cffi) with Playwright as escalation
Status: superseded 2026-10-22: a plain fetch with browser headers gets 200 from WG-Gesucht, and the
Worker cannot use curl-cffi. Revisit (Browser Rendering) if Cloudflare egress gets blocked.
Chose `curl_cffi` with `impersonate="chrome"` as primary fetcher (plain `requests` is reliably
blocked by WG-Gesucht's TLS-fingerprint check) with headless-Chromium Playwright only as a fallback
when curl-cffi fails and the `[browser]` extra is installed.
Cost accepted: a cat-and-mouse hack that can break when the site upgrades detection, and it doesn't
execute JS — an always-browser approach would be more robust but heavier and slower.

### Resolve true Warmmiete via a detail-page fetch, then re-filter
Status: settled (ported to `worker/src/wggesucht.ts`) · revisit-if WG-Gesucht exposes warm rent
reliably on the card, or detail-fetch volume triggers blocking. Note 2026-10-22: for the WG rooms in
the first live run the card figure equalled Gesamtmiete every time.
The search-card price is ambiguous (often just Kaltmiete, lower than real cost). Chose to treat the
card price as a permissive lower bound, fetch each candidate's detail page for the true warm rent,
and re-run the filter — over trusting the card (fast but systematically wrong) or guessing NK as a
fixed percentage (cheap but often wrong, Munich Nebenkosten varies widely).
Cost accepted: N extra HTTP requests per run (slower, more bot-detectable); the detail parser is
fragile HTML scraping that breaks on layout changes.

### 5 km radius search around Alte Heide instead of city-wide + district allowlist
Status: superseded 2026-10-22 by the routed e-bike filter around Garching (above).
`SEARCH_CENTER_LAT/LNG` + `SEARCH_RADIUS_M` is the authoritative location filter when set; clearing
the center falls back to a Munich + commutable-suburb allowlist. See `docs/wiki/decisions/radius-search.md`
for the full alternatives comparison if this needs revisiting.

<!-- TODO(alp): remaining wiki decisions (structured-output-fallback, resilience-and-safety,
human-in-the-loop-feedback, llm-wiki-knowledge-layer, web-dashboard-architecture, wide-eval-bands,
per-run-heartbeat, deterministic-core-llm-at-edges) not summarized here for space — see
docs/wiki/decisions/ if a task needs one of them. -->
