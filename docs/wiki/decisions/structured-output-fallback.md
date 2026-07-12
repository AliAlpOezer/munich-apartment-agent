---
type: decision
title: Structured-output-first with regex-JSON fallback + confidence escalation
description: Ask for schema-typed output first, but fall back to parsing JSON out of prose because free models often can't tool-call.
resource: src/apartment_agent/llm/router.py
tags: [decision, llm, structured-output, parsing]
timestamp: 2026-07-12T00:00:00Z
---

## Context

The assessment step needs *structured* data back (a fit score + confidence + summary), not free text. The clean way is LLM **tool calling** via `with_structured_output`. But the [free tier-1 models](free-first-tiered-routing.md) frequently can't tool-call reliably — the exact models we most want to use are the ones most likely to fail structured output.

## What we chose

**Try structured output first; on failure, fall back to prompting for JSON and parsing it with a regex** (`_parse_assessment` in `graph.py`). Independently, a **confidence accept-gate** (`confidence >= 0.5`) drives tier escalation regardless of which parse path succeeded.

## How it works (beginner-first)

1. `router.structured(..., schema=...)` asks the model to emit data matching a Pydantic schema.
2. If that throws (model can't tool-call, or emits junk), the code re-asks in plain text and extracts the JSON object with a regex, then validates it.
3. Either way, `_confident` checks the parsed confidence; if it's below 0.5 the router escalates to a stronger tier.

## Alternatives & trade-offs

- **Tool-calling only**: cleanest, type-safe, no brittle regex. **Trade-off**: eliminates most free models, forcing paid tiers — it defeats the free-first strategy.
- **Prose-only parsing (always regex JSON)**: works everywhere. **Trade-off**: no schema guarantees, more parse failures on capable models that *could* have given clean structured output.
- **Where the chosen design is WORSE**: it is **two code paths to maintain and reason about**, and structured output **loses token metadata** (only `calls` is counted, so token totals under-report — see [LLM tiering concept](../concepts/llm-tiering-and-structured-output.md)). We accept lower observability and more code for broad model compatibility.

## Why this serves the goal

It lets the cheap-first router actually use cheap models (which can't tool-call) without giving up structured data, and the confidence gate stops a low-quality cheap answer from slipping through.

## Revisit when

- Free models gain reliable tool-calling (drop the regex path).
- Token accounting for structured calls becomes important (find another metadata source).

## Related pages

- Concept: [LLM tiering & structured output](../concepts/llm-tiering-and-structured-output.md)
- Component: [LLM router](../components/llm-router.md)
- Related decision: [free-first tiered routing](free-first-tiered-routing.md)
