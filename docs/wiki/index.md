# munich-apartment-agent — knowledge wiki

Apartment-hunting agent for WG-Gesucht. **Since 2026-10-22 it runs as one Cloudflare Worker** (`worker/`: cron + Queues + D1 + a map dashboard) aimed at Garching (TUM + SAP), filtering on routed e-bike minutes; see [cloudflare-workers-hosting.md](decisions/cloudflare-workers-hosting.md). The pages below the two newest decisions describe the retired Python/LangGraph pipeline (box era), which is kept until its LLM ranking, wiki and feedback parts are ported.

**New here?** Read in this order: [LangGraph state machine](concepts/langgraph-state-machine.md) → [Warmmiete vs Kaltmiete](concepts/warmmiete-vs-kaltmiete.md) → [current state](state/current-state.md) → the [orchestration component](components/orchestration.md).

## State

- [current-state.md](state/current-state.md) — what works now (93 passed / 1 skipped, 30 commits), what shipped this session, open questions.

## Decisions

The core of this wiki. Each records the alternatives and honest trade-offs.

- [cloudflare-workers-hosting.md](decisions/cloudflare-workers-hosting.md) — one Worker (cron, queue, D1, static dashboard) replaces the box; invariants, seams, failure model (2026-10-22).
- [bike-time-filter.md](decisions/bike-time-filter.md) — routed e-bike minutes to TUM and SAP Garching decide; derived radius is a superset (2026-10-22).
- [deterministic-core-llm-at-edges.md](decisions/deterministic-core-llm-at-edges.md) — hard-coded pipeline; LLM only for enrichment + wiki prose, never planning.
- [free-first-tiered-routing.md](decisions/free-first-tiered-routing.md) — free models first, escalate to paid Claude only on error or low confidence.
- [warmmiete-detail-fetch.md](decisions/warmmiete-detail-fetch.md) — fetch the detail page to resolve true warm rent instead of trusting the card.
- [structured-output-fallback.md](decisions/structured-output-fallback.md) — structured-output-first, regex-JSON fallback, confidence-driven escalation.
- [local-sqlite-vs-supabase.md](decisions/local-sqlite-vs-supabase.md) — a single local SQLite file instead of managed Postgres. *Superseded by D1.*
- [tls-impersonation-scraping.md](decisions/tls-impersonation-scraping.md) — curl-cffi browser TLS impersonation, Playwright as escalation. *Superseded: plain fetch works.*
- [resilience-and-safety.md](decisions/resilience-and-safety.md) — transient-only retry, durable checkpointing, prompt-injection hygiene.
- [human-in-the-loop-feedback.md](decisions/human-in-the-loop-feedback.md) — learn taste from Telegram emoji reactions.
- [llm-wiki-knowledge-layer.md](decisions/llm-wiki-knowledge-layer.md) — compounding markdown wiki; code owns numbers, LLM owns prose.
- [radius-search.md](decisions/radius-search.md) — a 5 km radius instead of city-wide + district allowlist. *Superseded by bike-time-filter.*
- [web-dashboard-architecture.md](decisions/web-dashboard-architecture.md) — single-flight lock, header-token auth, vanilla-JS + polling.
- [wide-eval-bands.md](decisions/wide-eval-bands.md) — inclusive score bands, not exact-score assertions.
- [per-run-heartbeat.md](decisions/per-run-heartbeat.md) — a "still alive" Telegram message on empty runs (shipped this session).

## Components

- [orchestration.md](components/orchestration.md) — the graph, entry points, `Settings`, and data models (`graph.py` + `main.py` + `config.py` + `models.py`).
- [scraper.md](components/scraper.md) — WG-Gesucht adapter (`wg_gesucht.py`).
- [filter.md](components/filter.md) — pure match rules (`nodes/filter.py`).
- [llm-router.md](components/llm-router.md) — tiered LLM routing (`llm/router.py`).
- [database.md](components/database.md) — local SQLite store (`db/sqlite_client.py`).
- [notifications-and-feedback.md](components/notifications-and-feedback.md) — Telegram send + reaction ingest (`notify/telegram.py` + `feedback.py`).
- [wiki-layer.md](components/wiki-layer.md) — compounding markdown knowledge (`wiki/`).
- [web-dashboard.md](components/web-dashboard.md) — FastAPI + vanilla-JS SPA (`web/`).
- [evals.md](components/evals.md) — golden fit-eval + synthesis judge (`evals/`).

## Concepts

Cross-cutting beginner explainers, linked from the pages above instead of re-explaining.

- [langgraph-state-machine.md](concepts/langgraph-state-machine.md) — what LangGraph is; the pipeline as a graph.
- [warmmiete-vs-kaltmiete.md](concepts/warmmiete-vs-kaltmiete.md) — German warm/cold rent + Nebenkosten (critical domain concept).
- [llm-tiering-and-structured-output.md](concepts/llm-tiering-and-structured-output.md) — tiers, tokens, tool-calling, structured output.
- [settings-and-env-precedence.md](concepts/settings-and-env-precedence.md) — pydantic-settings `.env` > code default, and the move-in gotcha.

## History

- [log.md](log.md) — append-only history of documentation passes.
