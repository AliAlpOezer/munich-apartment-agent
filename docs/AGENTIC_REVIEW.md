# Agentic-engineering review

How "the stream" — the LangGraph pipeline
`scrape → filter → dedup → detail → enrich → persist → wiki → notify` — measures up against current
agentic-engineering conventions, and the roadmap to close the gaps. Statuses are flipped to ✅ as each
item lands.

## Status at a glance

| # | Item | Status |
|---|------|--------|
| 1 | Durable execution / checkpointing | ✅ done |
| 2 | Evals (golden set + LLM-as-judge) | ⏳ planned |
| 3 | Observability (run metrics + tracing) | ⏳ planned |
| 4 | Structured output + confidence escalation (C2) | ⏳ planned |
| 5 | Retries/backoff + prompt-injection hygiene | ⏳ planned |
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

### 2. Evals — golden set + LLM-as-judge — ⏳
**Convention.** A labelled dataset plus automated evals (assertions + LLM-as-judge) run in CI; prompts
are regression-tested and per-model quality is tracked so models can be swapped with confidence.
**Plan.** An `evals/` harness with a labelled dataset of listings (expected fit-score bands) and an
LLM-as-judge for synthesis coherence; runs offline against a fake model in tests, and against the live
router when keys are present.

### 3. Observability — run metrics + tracing — ⏳
**Convention.** OpenTelemetry GenAI semantic conventions: per-node spans with model, token usage,
latency, cost; run metrics persisted for trend analysis.
**Plan.** Capture per-node timings + token usage on `RunResult` and persist to a `runs` table; enable
LangSmith tracing via env (`LANGCHAIN_TRACING_V2`). Run history also feeds the wiki and the frontend.

### 4. Structured output + confidence escalation (was C2) — ⏳
**Convention.** Provider-native structured output / constrained decoding over regex-scraped JSON; and
difficulty-aware escalation, not failure-only.
**Plan.** Make `enrich` use `router.structured()` with a regex fallback for free models that can't
tool-call; let the router escalate on an `accept`/confidence predicate so a low-confidence cheap
result escalates a tier instead of being accepted.

### 5. Retries/backoff + prompt-injection hygiene — ⏳
**Convention.** Wrap flaky external calls in retry-with-jitter; treat scraped text as untrusted input.
**Plan.** `tenacity` retries on `fetch`/`fetch_costs`/LLM calls; delimit scraped fields as untrusted
data in prompts and keep outputs range-clamped.

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
