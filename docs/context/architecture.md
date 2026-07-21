# Architecture — munich-apartment-agent

## Shape

A LangGraph state machine runs the whole scrape-to-notify pipeline as 8 node closures over a `Deps`
dataclass: `scrape → filter → dedup → (detail → enrich → persist → wiki) → notify`. The only
conditional edge (`route_after_dedup` in `graph.py`) skips straight to `END` when dedup finds 0 new
listings — nothing downstream runs on an empty diff. `main.py` and the web dashboard both call the
same `_run_graph` / `run_pipeline` entry points, so the CLI (`python -m apartment_agent.main`,
scheduled every ~3h) and the "Search now" button in the dashboard drive an identical graph. State
(`Settings`, config, defaults) lives in `config.py`; core data types (`Listing`, `FilterConfig`,
`RunResult`) live in `models.py`. Config resolves `.env`/env var over code default (pydantic-settings,
`extra="ignore"`) — a value set in the deployed `.env` silently wins over anything changed in
`config.py`'s code default.

## Map

| Path | Holds |
|---|---|
| `src/apartment_agent/graph.py` | Graph builder, all 8 node closures, `route_after_dedup`, timing wrapper `_timed` |
| `src/apartment_agent/main.py` | CLI entry (`main`), shared `_run_graph`, checkpoint resume logic |
| `src/apartment_agent/config.py` | `Settings` (pydantic-settings, reads `.env`, `extra="ignore"`) |
| `src/apartment_agent/models.py` | `Listing`, `ListingType`, `FilterConfig`, `RunResult` |
| `src/apartment_agent/sources/` | Source-adapter pattern; `base.py` interface, `wg_gesucht.py` impl (curl-cffi + Playwright fallback) |
| `src/apartment_agent/nodes/filter.py` | Pure, unit-tested match rules (rent/size/move-in/radius) — no LLM |
| `src/apartment_agent/llm/router.py` | Tiered LLM router: free OpenRouter → OpenCode Zen → Claude, confidence-gated escalation |
| `src/apartment_agent/db/sqlite_client.py` | `ListingsDB` — self-initializing local SQLite, WAL mode, short-lived connections |
| `src/apartment_agent/notify/telegram.py` | Telegram send + `format_heartbeat` |
| `src/apartment_agent/feedback.py` | Ingests Telegram 👍/👎 reactions into learned preferences (`--sync-feedback`) |
| `src/apartment_agent/wiki/` | LLM-wiki pattern: `ingest.py`/`pages.py`/`store.py` maintain the runtime markdown wiki at `WIKI_DIR` (gitignored, separate from `docs/wiki/`); `lint.py` backs `--lint` |
| `src/apartment_agent/web/` | FastAPI dashboard (`app.py`) + vanilla-JS static SPA over the same SQLite `DB_PATH`; single-flight lock on manual runs |
| `src/apartment_agent/evals/` | `harness.py` — fit-score evals against live LLM tiers; golden `cases.py` |
| `src/apartment_agent/checkpoint.py`, `retry.py` | LangGraph SQLite checkpointing (resume interrupted runs); tenacity-based transient retry |
| `deploy/systemd/` | `install.sh` (3h timer) and `install-dashboard.sh` (dashboard service) for the box deploy path |
| `docs/wiki/` | Deep human-oriented knowledge base (one page per decision/component/concept) — not the runtime wiki above |

## Boundaries

- Filtering (`nodes/filter.py`) is pure and deterministic — no LLM call. The LLM only ranks fit and
  writes prose (enrich + wiki nodes); it never decides control flow.
- Scraping goes through the `sources/base.py` adapter interface — adding a new site (e.g.
  ImmoScout24) is a new subclass, not a change to the graph.
- The agent's 3h timer and the web dashboard share both `DB_PATH` and `checkpoint_db` from the
  same `.env`; they don't collide because each `_run_graph` call opens a fresh `thread_id`
  (`checkpoint.py`), not a per-caller checkpoint file.
- `.env` values always win over `config.py` code defaults when both are set (pydantic-settings
  precedence).

## External dependencies

- **WG-Gesucht** (scrape target) — via `curl-cffi` (Chrome TLS impersonation) with an optional
  Playwright headless-browser fallback (`browser` extra) when curl-cffi is blocked.
- **OpenRouter** (tier 1, free), **OpenCode Zen** (tier 2), **Anthropic Claude** (tier 3) — LLM
  providers, escalated in order on error or low confidence.
- **Telegram Bot API** (via `httpx`) — outbound notifications and heartbeats; inbound 👍/👎 reaction
  polling for feedback.
- **Local SQLite** — no external DB; both the listings store and the LangGraph checkpoint store are
  local files, gitignored.
