---
type: component
title: Orchestration (graph.py + main.py + config.py + models.py)
description: The pipeline graph, its entry points, the Settings config object, and the core data models.
resource: src/apartment_agent/graph.py
tags: [component, orchestration, langgraph, config, models]
timestamp: 2026-07-12T00:00:00Z
---

## What it does

Assembles and runs the whole scrape-to-notify pipeline as a LangGraph graph, exposes the entry points the CLI and web dashboard call, and defines the shared config (`Settings`) and data types (`Listing`, `FilterConfig`, `RunResult`). Read the [LangGraph state machine concept](../concepts/langgraph-state-machine.md) first if graphs are new to you.

## Where it lives

- `src/apartment_agent/graph.py` — graph builder + all 8 node closures.
- `src/apartment_agent/main.py` — entry points.
- `src/apartment_agent/config.py` — `Settings`.
- `src/apartment_agent/models.py` — data models.

## Interface

### graph.py
- Nodes (closures over a `Deps` dataclass): `scrape`, `filter`, `dedup`, `detail`, `enrich`, `persist`, `wiki`, `notify`.
- `route_after_dedup(state) -> "detail" | "END"` (`graph.py:293`) — the only conditional edge; skips to `END` when 0 new.
- `_timed(name, fn)` (`graph.py:298`) — wraps a node to record wall-time into `result.node_timings_ms` in a `finally` block.
- Wiring at `graph.py:310-323`; compiled with an optional checkpointer (`graph.py:324`).

### main.py
- `run_pipeline(settings) -> RunResult` — the web dashboard's entry point.
- `_run_graph(settings, *, heartbeat_on_empty=False) -> dict` (`main.py:61`) — shared core for CLI and web. When `heartbeat_on_empty` is set and a run finds 0 new listings, it sends a Telegram heartbeat (`main.py:98`).
- `main(argv)` — CLI entry; calls `_run_graph(..., heartbeat_on_empty=True)` (`main.py:197`) so scheduled runs always report in. The web "Search now" path leaves it off.
- Checkpointing: when `enable_checkpointing` and not `dry_run`, opens `SqliteSaver(checkpoint_db)`, calls `resume_incomplete(graph)` before the new run, then invokes with a fresh `thread_id`.

### models.py (pydantic + stdlib only)
- `ListingType` enum: `WG_ROOM` / `APARTMENT` / `UNKNOWN`.
- `Listing`: identity (`source`, `external_id`, `url`, `title`); prices (`price_warm`, `price_cold`, `price_listed` [transient, not persisted]); `size_sqm`, `rooms`, `listing_type`; `district`, `address`, `city`; `available_from`, `available_to`, `posted_at`; `fit_score`, `summary`; `raw`.
- `Listing.effective_warm_rent` (`models.py:54`) — first of `price_warm`, `price_cold`, `price_listed`; a permissive lower bound. See [Warmmiete vs Kaltmiete](../concepts/warmmiete-vs-kaltmiete.md).
- `FilterConfig`: cap / min-size / move-in; window `available_from_before_grace_days=14`, `available_from_after_window_days=92`; `listing_types`; `allowed_locations` (city-wide only); radius fields + `has_radius` property.
- `RunResult`: counters `scraped`/`parsed`/`matched`/`new`/`notified`, `errors[]`, timestamps, `node_timings_ms`, `tokens`, `duration_ms`.

## Settings (config.py) — full key list with defaults

`Settings` is a **pydantic-settings** class reading `.env` (`extra="ignore"`). See the precedence rule and gotcha in [settings-and-env-precedence](../concepts/settings-and-env-precedence.md).

| Key | Default |
|---|---|
| `openrouter_api_key` | "" |
| `openrouter_base_url` | openrouter.ai/api/v1 |
| `tier1_models` | openrouter/free + nvidia nemotron + qwen3-next + llama-3.3-70b (all `:free`) |
| `opencode_zen_api_key` | "" |
| `opencode_zen_base_url` | opencode.ai/zen/v1 |
| `tier2_model` | "" |
| `anthropic_api_key` | "" |
| `tier3_model` | claude-sonnet-4-6 |
| `db_path` | apartments.sqlite |
| `telegram_bot_token` | "" |
| `telegram_chat_id` | "" |
| `max_warm_rent_eur` | 657.0 |
| `min_size_sqm` | 10.0 |
| `move_in_date` | 2026-09-01 |
| `listing_types` | wg_room, apartment |
| `search_center_label` | Alte Heide … 80805 |
| `search_center_lat` | 48.1783353 |
| `search_center_lng` | 11.5978799 |
| `search_radius_m` | 5000 |
| `dry_run` | False |
| `enable_detail_fetch` | True |
| `detail_concurrency` | 3 |
| `enable_llm_enrich` | True |
| `enable_wiki` | True |
| `enable_feedback` | True |
| `enable_checkpointing` | True |
| `checkpoint_db` | agent_state.sqlite |
| `web_auto_search_minutes` | 180 |
| `web_api_token` | "" |
| `web_cors_origins` | "*" |
| `wiki_dir` | wiki |
| `log_level` | INFO |

Helpers: `filter_config()`, `tier1_model_list`, `cors_origin_list`.

## Related pages

- Concepts: [LangGraph state machine](../concepts/langgraph-state-machine.md), [settings & env precedence](../concepts/settings-and-env-precedence.md)
- Decision: [deterministic core, LLM at the edges](../decisions/deterministic-core-llm-at-edges.md), [per-run heartbeat](../decisions/per-run-heartbeat.md)
- Downstream components: [scraper](scraper.md), [filter](filter.md), [database](database.md), [notifications & feedback](notifications-and-feedback.md), [wiki layer](wiki-layer.md)
