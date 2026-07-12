---
type: concept
title: LLM tiering and structured output
description: Plain-English explainer of what an LLM is here, what "tiers" and "structured output" mean, and why free models need a fallback.
resource: src/apartment_agent/llm/router.py
tags: [llm, routing, structured-output, beginner]
timestamp: 2026-07-12T00:00:00Z
---

## Vocabulary, defined once

- **LLM (Large Language Model)**: a text-in / text-out model (e.g. Claude, Llama). You send a *system* message (instructions) and a *user* message (the data), and it returns generated text.
- **Prompt**: the text you send. Split here into a *system* prompt (role/rules) and a *user* prompt (the listing to assess).
- **Token**: the unit an LLM reads/writes in — roughly ¾ of a word. Providers bill per input+output token, so token count ≈ cost.
- **Tier**: in this project, a price/capability band of models. `CHEAP=1` (free OpenRouter models), `MEDIUM=2` (OpenCode Zen), `HARD=3` (Anthropic Claude). Defined as an `IntEnum` so tiers are ordered integers you can compare and climb.
- **Structured output**: asking the LLM to return data that conforms to a fixed schema (here a Pydantic model) instead of free prose — so downstream code can rely on the shape.
- **Tool calling / function calling**: a model capability where it emits a structured "call" matching a schema you gave it. `with_structured_output(...)` uses this under the hood. Many *free* models cannot do it reliably.

## Escalation, in two dimensions

The [`ModelRouter`](../components/llm-router.md) tries the cheapest option first and climbs only when needed. There are two independent axes:

1. **Within a tier (rotate on error)**: tier 1 lists several free models. Free models throttle (HTTP 429) per upstream provider, so on a transient error the router rotates to the *next model in the same tier*.
2. **Across tiers (escalate on error OR low quality)**: if a whole tier fails, or if the answer fails an `accept(...)` quality gate, the router steps up to the next tier. For listing assessment the gate is `_confident` — accept only if the model's self-reported `confidence >= 0.5`.

So a low-confidence free answer is *rejected* and the request is retried on a stronger, costlier model — you pay for Claude only when the cheap models genuinely can't do it.

## Structured-output-first, regex-JSON fallback

The router first tries real structured output. If that fails (common on free models that can't tool-call), the code falls back to asking for JSON in plain text and parsing it with a regex (`_parse_assessment` in `graph.py`). See the decision [structured-output-first with regex fallback](../decisions/structured-output-fallback.md).

> **Caveat worth knowing**: when structured output *does* work, the token metadata is lost — the router can only bump the `calls` counter, not `input_tokens`/`output_tokens`. So token totals under-count structured calls.

## Related pages

- Component: [LLM router](../components/llm-router.md)
- Decisions: [free-first tiered routing](../decisions/free-first-tiered-routing.md), [structured-output-first with regex fallback](../decisions/structured-output-fallback.md)
