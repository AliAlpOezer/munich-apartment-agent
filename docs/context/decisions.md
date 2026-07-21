# Decisions — munich-apartment-agent

One entry per settled decision, drawn from `docs/wiki/decisions/` (full rationale there if needed,
but this file is self-contained). Newest first by wiki pass date (2026-07-12).

### Local SQLite instead of Supabase / managed Postgres
Status: settled · revisit-if multiple machines/writers need the same data, or data loss becomes
costly enough to need managed backups.
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
Status: settled · revisit-if impersonation starts getting blocked routinely, or listing data moves
behind client-side JS.
Chose `curl_cffi` with `impersonate="chrome"` as primary fetcher (plain `requests` is reliably
blocked by WG-Gesucht's TLS-fingerprint check) with headless-Chromium Playwright only as a fallback
when curl-cffi fails and the `[browser]` extra is installed.
Cost accepted: a cat-and-mouse hack that can break when the site upgrades detection, and it doesn't
execute JS — an always-browser approach would be more robust but heavier and slower.

### Resolve true Warmmiete via a detail-page fetch, then re-filter
Status: settled · revisit-if WG-Gesucht exposes warm rent reliably on the card, or detail-fetch
volume triggers blocking.
The search-card price is ambiguous (often just Kaltmiete, lower than real cost). Chose to treat the
card price as a permissive lower bound, fetch each candidate's detail page for the true warm rent,
and re-run the filter — over trusting the card (fast but systematically wrong) or guessing NK as a
fixed percentage (cheap but often wrong, Munich Nebenkosten varies widely).
Cost accepted: N extra HTTP requests per run (slower, more bot-detectable); the detail parser is
fragile HTML scraping that breaks on layout changes.

### 5 km radius search around Alte Heide instead of city-wide + district allowlist
Status: settled.
`SEARCH_CENTER_LAT/LNG` + `SEARCH_RADIUS_M` is the authoritative location filter when set; clearing
the center falls back to a Munich + commutable-suburb allowlist. See `docs/wiki/decisions/radius-search.md`
for the full alternatives comparison if this needs revisiting.

<!-- TODO(alp): remaining wiki decisions (structured-output-fallback, resilience-and-safety,
human-in-the-loop-feedback, llm-wiki-knowledge-layer, web-dashboard-architecture, wide-eval-bands,
per-run-heartbeat, deterministic-core-llm-at-edges) not summarized here for space — see
docs/wiki/decisions/ if a task needs one of them. -->
