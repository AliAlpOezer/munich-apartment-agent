# Agentic-engineering review

How "the stream" — the LangGraph pipeline
`scrape → filter → dedup → detail → enrich → persist → wiki → notify` — measures up against current
agentic-engineering conventions, and the roadmap to close the gaps. Statuses are flipped to ✅ as each
item lands.

## Status at a glance

| # | Item | Status |
|---|------|--------|
| 1 | Durable execution / checkpointing | ✅ done |
| 2 | Evals (golden set + LLM-as-judge) | ✅ done |
| 3 | Observability (run metrics + tracing) | ✅ done |
| 4 | Structured output + confidence escalation (C2) | ✅ done |
| 5 | Retries/backoff + prompt-injection hygiene | ✅ done |
| 6 | Human-in-the-loop feedback loop | ⏳ planned |
| 7 | Bounded-concurrency fan-out | ⏳ planned |

## What's already aligned with modern practice
- **Deterministic shell, stochastic core at the edges.** Parsing/filtering/dedup/wiki-stats are pure
  and unit-tested; the LLM only ranks fit and writes prose, minimizing its blast radius.
- **Tiered routing with graceful degradation** (free → medium → premium, intra-tier rotation).
- **A long-term semantic memory** — the LLM-Wiki layer, not a stateless feed.
- **Output validation** — `fit_score` is clamped to 0–100.

## The gaps and the plan

### 1. Durable execution / checkpointing — ✅
**Convention.** Agentic graphs run on a checkpointer so a crash mid-run resumes instead of
restarting; it also unlocks time-travel debugging and human-in-the-loop interrupts.
**Implemented.** `build_graph(deps, checkpointer=...)` compiles with a `SqliteSaver`; `checkpoint.py`
adds `resume_incomplete()`, which finishes any thread left with pending next-nodes before a fresh run
starts. `ENABLE_CHECKPOINTING` / `CHECKPOINT_DB`.

### 2. Evals — golden set + LLM-as-judge — ✅
**Convention.** A labelled dataset plus automated evals (assertions + LLM-as-judge) run in CI; prompts
are regression-tested and per-model quality is tracked so models can be swapped with confidence.
**Implemented.** `apartment_agent.evals` holds a hand-labelled golden set (`GOLDEN`) with expected
fit-score bands and a harness: `run_fit_evals` exercises the real `assess_listing` path and checks
each band; `judge_synthesis` is an LLM-as-judge for wiki-synthesis groundedness. Runs offline against
fake routers in `tests/test_evals.py`, and live via `python -m apartment_agent.evals.harness`.

### 3. Observability — run metrics + tracing — ✅
**Convention.** OpenTelemetry GenAI semantic conventions: per-node spans with model, token usage,
latency, cost; run metrics persisted for trend analysis.
**Implemented.** Each node is wrapped to record wall time on `RunResult.node_timings_ms`; the router
accumulates token usage (`router.usage`). After each run the metrics persist to a new `runs` table
(`run_to_row` + `ListingsDB.record_run`). LangSmith tracing is opt-in via `LANGCHAIN_TRACING_V2`.

### 4. Structured output + confidence escalation (was C2) — ✅
**Convention.** Provider-native structured output / constrained decoding over regex-scraped JSON; and
difficulty-aware escalation, not failure-only.
**Implemented.** `complete()`/`structured()` take an `accept` predicate; a result that fails it
escalates to the next tier (and the last result is returned as a best effort if none pass).
`assess_listing` tries `router.structured(Assessment)` first and falls back to regex JSON for free
models that can't tool-call; the `Assessment.confidence` field drives escalation below `0.5`.

### 5. Retries/backoff + prompt-injection hygiene — ✅
**Convention.** Wrap flaky external calls in retry-with-jitter; treat scraped text as untrusted input.
**Implemented.** `retry.py`'s `network_retry` (exponential + jitter, reraises the original error)
wraps `WgGesuchtAdapter.fetch` and the router's per-model invoke. Scraped fields go inside a
`<listing>` block with the enrich/wiki system prompts instructing the model to treat them as data,
never instructions; `fit_score` stays range-clamped.

### 6. Human-in-the-loop feedback loop — ⏳
**Convention.** HITL feedback becomes procedural memory that tunes the agent.
**Plan.** Sync Telegram 👍/👎 reactions (`--sync-feedback`), store them, and fold them into the wiki
`preferences` page so the search intent learns over time.

### 7. Bounded-concurrency fan-out — ⏳
**Convention.** Concurrent fan-out for I/O-bound steps, bounded to stay polite.
**Plan.** Run `detail` fetches on a small bounded thread pool (`DETAIL_CONCURRENCY`), preserving
per-request jitter.

## Principles to preserve going forward
- Keep the LLM at the edges; never let it author numbers or control flow.
- Every model-touching change ships with an eval.
- Treat all scraped/user content as untrusted data, never as instructions.
- Log what was dropped/capped — no silent truncation.
