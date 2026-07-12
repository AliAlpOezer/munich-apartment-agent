---
type: decision
title: Free-first tiered LLM routing with confidence-driven escalation
description: Try free models first and escalate to paid Claude only when a cheaper answer is missing or low-confidence.
resource: src/apartment_agent/llm/router.py
tags: [decision, llm, routing, cost]
timestamp: 2026-07-12T00:00:00Z
---

## Context

Every listing gets an LLM assessment, and the agent runs every ~3h indefinitely. Naively calling a premium model each time is real, recurring money for a hobby-scale job. But the cheapest (free) models are also the least reliable.

## What we chose

A **three-tier router** (see [LLM tiering concept](../concepts/llm-tiering-and-structured-output.md)): `CHEAP=1` free OpenRouter models → `MEDIUM=2` OpenCode Zen → `HARD=3` Anthropic Claude. Start cheap; escalate on error *or* on a low-confidence answer (accept gate `confidence >= 0.5`).

## How it works (beginner-first)

`ModelRouter.complete(...)` walks candidates low→high. Two independent moves:
- **Within a tier**: free models throttle (HTTP 429) per upstream, so on an error the router rotates to a sibling free model.
- **Across tiers**: if the tier fails outright, or the answer fails the `accept` predicate, it steps up. So Claude is reached only for the hard or rejected cases — most listings never leave tier 1.

## Alternatives & trade-offs

- **Always-Claude (single premium model)**: simplest, highest and most consistent quality. **Trade-off**: recurring cost on every listing forever; overkill for easy cases.
- **Single free model, no escalation**: zero cost. **Trade-off**: brittle — one throttled or dumb model silently degrades every assessment with no recovery.
- **Where the chosen design is WORSE**: it is more complex (two escalation axes, an accept gate, per-tier model lists) and its **latency is variable and occasionally high** — a hard listing may traverse several throttled free models before landing on Claude. A single good model would answer once, fast. We trade tail latency and code complexity for near-zero average cost.

## Why this serves the goal

Keeps a perpetually-running agent essentially free in the common case while still buying a correct answer (Claude) exactly when it's needed. Cost scales with difficulty, not with volume.

## Revisit when

- Free tiers get so rate-limited that escalation dominates (then just pay for MEDIUM by default).
- Assessment quality on tier 1 proves unacceptable in evals.

## Related pages

- Concept: [LLM tiering & structured output](../concepts/llm-tiering-and-structured-output.md)
- Component: [LLM router](../components/llm-router.md)
- Related decision: [structured-output-first with regex fallback](structured-output-fallback.md)
