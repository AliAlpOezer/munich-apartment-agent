---
type: decision
title: Deterministic core, LLM only at the edges
description: The pipeline's control flow is hard-coded; the LLM is used only for enrichment and wiki prose, never to plan or route.
resource: src/apartment_agent/graph.py
tags: [decision, architecture, langgraph, llm]
timestamp: 2026-07-12T00:00:00Z
---

## Context

An "agent" can mean two very different things. One kind lets an LLM decide *what to do next* at each step (an LLM planner). The other hard-codes the workflow and calls an LLM only for specific narrow judgements. This project had to pick.

## What we chose

A **fixed, deterministic pipeline** (the [LangGraph state machine](../concepts/langgraph-state-machine.md)) where control flow is code. The LLM is confined to two edges: **enrichment** (scoring a listing's fit) and **wiki prose synthesis**. The LLM never chooses the next node.

## How it works (beginner-first)

The graph `START → scrape → filter → dedup → detail → enrich → persist → wiki → notify → END` is wired by hand in `graph.py:315-323`. The only branch, `route_after_dedup` (`graph.py:293`), is a plain `if state["new"]` — a code condition, not an LLM decision. So on a run with 0 new listings, the pipeline provably skips all detail/LLM/DB work. Everything expensive or risky is deterministic; the LLM is a leaf-level helper.

## Alternatives & trade-offs

- **LLM-driven planner (agent picks next action)**: more flexible and impressive; can adapt to surprises. **Trade-offs**: non-deterministic control flow is hard to test, can loop or burn tokens, and can make an unrecoverable choice. For a fixed daily job (scrape → filter → notify) this flexibility buys almost nothing and costs reliability.
- **Where the chosen design is WORSE**: it cannot adapt on its own. If WG-Gesucht changes its page layout, a planner *might* improvise around it; this pipeline will just fail the scrape node and needs a human code fix. The determinism we gained is paid for in adaptability we gave up.

## Why this serves the goal

The goal is an unattended agent that runs every ~3h for months and can be trusted while the user sleeps. Testable, bounded, resumable control flow matters far more than cleverness. Predictability is the feature.

## Revisit when

- The task space becomes genuinely open-ended (e.g. multi-site negotiation, or reacting to replies).
- Scrape targets change often enough that hand-fixing nodes becomes the bottleneck.

## Related pages

- Concept: [LangGraph state machine](../concepts/langgraph-state-machine.md)
- Component: [orchestration](../components/orchestration.md)
