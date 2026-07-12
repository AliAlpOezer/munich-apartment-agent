---
type: concept
title: LangGraph state machine (the pipeline as a graph)
description: A one-page explainer of what LangGraph is and how this project models one scrape-to-notify run as a directed graph of nodes.
resource: src/apartment_agent/graph.py
tags: [langgraph, orchestration, python, beginner]
timestamp: 2026-07-12T00:00:00Z
---

## What LangGraph is (one sentence)

**LangGraph** is a Python library for wiring a program together as a *graph* of steps — you register **nodes** (plain functions) and **edges** (which node runs after which), then hand it an input and it walks the graph for you.

If you come from Node: think of it like a hard-coded workflow engine, closer to an Express middleware chain or a Temporal workflow than to Express routing. There is no HTTP; a "run" is one traversal of the graph from `START` to `END`.

## Terms of art, defined once

- **Node**: a function that takes the current shared state and returns a partial update to it. Here every node is a small function like `scrape`, `filter`, `dedup`.
- **State**: a single dictionary passed to every node. In this repo it is `AgentState` (a `TypedDict` — a dict whose keys/types are declared for the type-checker). Nodes read from it and return dict fragments that get merged in.
- **Edge**: "after node A, run node B." A **conditional edge** is "after A, look at the state and pick B *or* C."
- **Compile**: turning the assembled node+edge definition into a runnable object (`g.compile(...)`).
- **Invoke**: running one traversal.

## How this project uses it

The whole pipeline is one graph, built in [`graph.py`](../components/orchestration.md):

```
START → scrape → filter → dedup ─(new?)─► detail → enrich → persist → wiki → notify → END
                                └────────── 0 new ───────────────────────────────► END
```

- The eight nodes are registered in `graph.py:310-314`.
- Almost all edges are plain "A then B" (`graph.py:315-323`).
- There is exactly **one** conditional edge, `route_after_dedup` (`graph.py:293-294`): if `dedup` found new listings it goes to `detail`; otherwise it jumps straight to `END`. This is the whole point of the design — when there is nothing new, the expensive work (detail-page fetches, LLM calls, DB writes) is skipped. See the decision [deterministic core, LLM at the edges](../decisions/deterministic-core-llm-at-edges.md).

### Closures and Deps

Each node is created as a **closure** (a function that "remembers" variables from where it was defined) over a `Deps` dataclass holding the settings, filter config, scraper adapters, the optional LLM router, DB client, notifier, and wiki ingestor. So a node can call `deps.db` or `deps.notifier` without those being global.

### `_timed` wrapper (observability)

Every node is wrapped by `_timed` (`graph.py:298-307`), which records the node's wall-clock time in milliseconds into `result.node_timings_ms` inside a `finally` block — so timing is captured even if the node throws.

### Checkpointing

Optionally the graph is compiled with a **checkpointer** (`SqliteSaver`) that saves state after each node to a SQLite file, so a run that crashed mid-way can be resumed. See the [resilience & safety decision](../decisions/resilience-and-safety.md), which covers `resume_incomplete`.

## Related pages

- Component: [orchestration (graph.py + main.py)](../components/orchestration.md)
- Decision: [deterministic core, LLM only at the edges](../decisions/deterministic-core-llm-at-edges.md)
