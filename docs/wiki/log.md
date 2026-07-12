# Wiki log

Append-only history of documentation passes. Newest first.

## 2026-07-12 — initial knowledge-wiki bundle

First pass. Created the full bundle: 1 index, this log, 1 state page, 13 decision pages, 9 component pages, 4 concept pages.

**Pages created**
- state: `current-state.md`
- decisions: `deterministic-core-llm-at-edges`, `free-first-tiered-routing`, `warmmiete-detail-fetch`, `structured-output-fallback`, `local-sqlite-vs-supabase`, `tls-impersonation-scraping`, `resilience-and-safety`, `human-in-the-loop-feedback`, `llm-wiki-knowledge-layer`, `radius-search`, `web-dashboard-architecture`, `wide-eval-bands`, `per-run-heartbeat`
- components: `orchestration`, `scraper`, `filter`, `llm-router`, `database`, `notifications-and-feedback`, `wiki-layer`, `web-dashboard`, `evals`
- concepts: `langgraph-state-machine`, `warmmiete-vs-kaltmiete`, `llm-tiering-and-structured-output`, `settings-and-env-precedence`

**Evidence sources**
- The session codebase digest (2026-07-12) for pipeline shape, component internals, and design rationale.
- `git log` — verified commit count **30** (`git log --oneline | wc -l`); confirmed HEAD is `2327809` and `git log origin/main..HEAD` shows **0** ahead (the digest's "one ahead, unpushed" note is now resolved — the fix is pushed).
- Test run — **93 passed, 1 skipped** (the 1 skip is the `RUN_LIVE_EVALS`-gated live eval).
- Spot-checked files for citations: `graph.py:293` (`route_after_dedup`), `graph.py:298-323` (`_timed` + wiring), `models.py:54-66` (`effective_warm_rent`), `notify/telegram.py:62-70` (`format_heartbeat`), `main.py:61/98/197` (`_run_graph` + heartbeat), `nodes/filter.py:30` (`passes_filter`), `pyproject.toml` (dependencies), package layout under `src/apartment_agent/`.
- Live-session diagnostics: deployment on "alpiclawd" (systemd timer + dashboard units), the Tailscale MTU black hole (≤~1028 B pass / ≥~1228 B drop), the broken HTTPS dashboard URL (proxy → dead port 18789 vs app on 8000), and the constant scraped=18/matched=12/new=0 anomaly over 18+ hours.
