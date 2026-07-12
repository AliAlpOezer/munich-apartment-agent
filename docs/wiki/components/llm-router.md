---
type: component
title: LLM router
description: Routes each LLM request through cheap→medium→hard model tiers, rotating within a tier on errors and escalating across tiers on error or low confidence.
resource: src/apartment_agent/llm/router.py
tags: [component, llm, routing, tiering, structured-output]
timestamp: 2026-07-12T00:00:00Z
---

## What it does

Given a prompt and a target tier, tries the cheapest models first and climbs only as far as it must to get an acceptable answer. Read [LLM tiering & structured output](../concepts/llm-tiering-and-structured-output.md) for the vocabulary.

## Where it lives

`src/apartment_agent/llm/router.py`.

## Interface

- `Tier(IntEnum)`: `CHEAP=1` (OpenRouter free), `MEDIUM=2` (OpenCode Zen), `HARD=3` (Anthropic Claude, or Claude-via-Zen if no Anthropic key).
- `ModelRouter.complete(system, user, *, tier, max_tier, accept) -> str` — tries candidates low→high; `accept(content)` is a predicate that gates success and drives escalation.
- `ModelRouter.structured(..., schema, ...)` — same, but via LangChain's `with_structured_output` into a Pydantic schema.
- `usage = {calls, input_tokens, output_tokens}` — running totals. **Structured output loses token metadata** (only bumps `calls`).
- `_invoke` is wrapped in `@network_retry(attempts=2)`.

## Current implementation

- Chat clients (`ChatOpenAI` / `ChatAnthropic`) are **lazy-built and cached**, configured `temperature=0`, `timeout=90`, `max_retries=0` (retries are handled by `network_retry`, not the SDK).
- **Two-dimensional escalation**:
  - *Within a tier, on error*: rotate to the next model in the same tier (free models throttle per upstream provider, so a sibling model may still answer).
  - *Across tiers, on error OR low `accept`*: step up to the next tier.
- The listing-assessment caller, `assess_listing` in `graph.py`, uses `accept=_confident` (accept only if `confidence >= 0.5`).
- **Structured-output-first, then regex-JSON fallback** (`_parse_assessment`) — free models often can't tool-call, so if structured output fails the code parses JSON out of plain text. See the [decision](../decisions/structured-output-fallback.md).

## Config / Settings keys that tune it

- `tier1_models` (free OpenRouter list), `openrouter_api_key`, `openrouter_base_url`.
- `tier2_model`, `opencode_zen_api_key`, `opencode_zen_base_url`.
- `tier3_model` (claude-sonnet-4-6), `anthropic_api_key`.
- `enable_llm_enrich` toggles the LLM step entirely.

## Related pages

- Concept: [LLM tiering & structured output](../concepts/llm-tiering-and-structured-output.md)
- Decisions: [free-first tiered routing](../decisions/free-first-tiered-routing.md), [structured-output-first with regex fallback](../decisions/structured-output-fallback.md)
- Uses: [resilience (network_retry)](../decisions/resilience-and-safety.md)
