---
type: component
title: Evals (fit-scoring + synthesis judging)
description: A tiny golden-case harness that runs the real assessment path with wide inclusive score bands, plus an LLM-as-judge for wiki prose.
resource: src/apartment_agent/evals/
tags: [component, evals, testing, llm-as-judge]
timestamp: 2026-07-12T00:00:00Z
---

## What it does

Checks that the LLM's listing-assessment behaviour and wiki synthesis stay sane over time. An **eval** is an automated quality test for an LLM step — like a unit test, but tolerant of the model's non-determinism.

## Where it lives

`src/apartment_agent/evals/` (`cases.py`, `harness.py`).

## Interface

- `EvalCase(name, listing, lo, hi)` — a labeled listing plus an *inclusive band* `[lo, hi]` the fit score must land in.
- `GOLDEN` — **4** hand-labeled cases with deliberately **wide** bands.
- `run_fit_evals(...)` — runs the **real production** `assess_listing` path (not a stub), so it also catches integration regressions.
- `judge_synthesis(...)` — an **LLM-as-judge**: a stronger model grades the wiki prose. Runs `MEDIUM → HARD`; **defaults `grounded=false` on a parse failure** (fail-safe: unparseable = not proven grounded).

## Running it

- CLI: `python -m apartment_agent.evals` — exits `0` **iff** `pass_rate == 1.0`.
- Offline: pytest uses **fake routers** (fast, deterministic, no network/keys).
- Live: gated by the `RUN_LIVE_EVALS` environment variable (this is the **1 skipped** test in the suite — see [current state](../state/current-state.md)).

## Related pages

- Decision: [wide golden eval bands vs exact-score assertions](../decisions/wide-eval-bands.md)
- Exercises: [LLM router](llm-router.md), [wiki layer](wiki-layer.md)
