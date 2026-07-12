---
type: decision
title: Wide golden eval bands vs exact-score assertions
description: Assert that a fit score falls inside a generous range, not that it equals a fixed number.
resource: src/apartment_agent/evals/
tags: [decision, evals, testing, llm]
timestamp: 2026-07-12T00:00:00Z
---

## Context

The eval suite checks that the LLM's listing fit-scoring stays reasonable over time (see the [evals component](../components/evals.md)). But LLM outputs are **non-deterministic** — the same listing can score 7 one day and 8 the next. How strict should the assertion be?

## What we chose

**Wide, inclusive bands.** Each `EvalCase` carries a `[lo, hi]` range, and the 4 hand-labeled `GOLDEN` cases use deliberately generous bands. A case passes if the score lands anywhere inside its band. The CLI exits `0` only if all 4 pass.

## How it works (beginner-first)

`run_fit_evals` runs the **real production** `assess_listing` path (not a mock), so an eval also catches integration regressions — a broken prompt or router bug shows up as an out-of-band score, not just a "wrong number." A separate `judge_synthesis` uses an LLM-as-judge (`MEDIUM→HARD`) for wiki prose and defaults `grounded=false` if it can't parse the verdict.

## Alternatives & trade-offs

- **Exact-score assertions** (score must equal 8): maximally precise, pins behaviour tightly. **Trade-off**: **flaky** against a non-deterministic model — the suite would fail on normal run-to-run variance, training the maintainer to ignore red, which defeats the point of a test.
- **No fit evals (only unit tests on the deterministic code)**: nothing flaky, nothing to tune. **Trade-off**: a prompt or model regression that silently degrades scoring would go completely undetected.
- **Where the chosen design is WORSE**: wide bands are a **coarse safety net** — a real quality *drift* that stays inside the generous band passes unnoticed. Exact assertions would catch subtle regressions that wide bands wave through. We trade sensitivity for stability, because a flaky eval that's always ignored catches nothing at all.

## Why this serves the goal

A green suite must mean "still fine," not "got lucky today." Bands wide enough to tolerate normal LLM variance but tight enough to catch a real break give a signal the maintainer will actually trust.

## Revisit when

- Bands are so wide they'd pass an obviously-broken model (tighten them).
- The model becomes more deterministic (e.g. pinned + `temperature=0` proves stable enough for tighter bands).

## Related pages

- Component: [evals](../components/evals.md)
- Concept: [LLM tiering & structured output](../concepts/llm-tiering-and-structured-output.md)
