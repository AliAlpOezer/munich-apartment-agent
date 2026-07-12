---
type: decision
title: Resilience & safety (retry, checkpointing, prompt-injection hygiene)
description: Retry only transient failures, checkpoint runs so they can resume, and treat all scraped text as untrusted data.
resource: src/apartment_agent/retry.py
tags: [decision, resilience, retry, checkpointing, security, prompt-injection]
timestamp: 2026-07-12T00:00:00Z
---

## Context

An unattended agent that scrapes the web and calls LLMs faces flaky networks, throttling, crashes mid-run, and adversarial text on the pages it reads. Three related choices harden it.

## What we chose

1. **Transient-only retry** — retry timeouts/connection errors/429/5xx; **fail fast on 4xx**.
2. **Durable checkpointing** — save state after each node so an interrupted run resumes.
3. **Prompt-injection hygiene** — wrap all scraped text as untrusted data.

## How it works (beginner-first)

### 1. Retry (`retry.py`)
`network_retry(attempts=3, max_wait=15)` uses **tenacity** (a retry library) with exponential backoff + jitter and `reraise=True`. `is_transient` decides what to retry: `Timeout` / `Connection` / **429** / **≥500** are retried; **permanent 4xx fail fast** (so the [LLM router](../components/llm-router.md) can escalate instead of pointlessly retrying a bad request); unknown errors are treated as retryable.

### 2. Checkpointing (`checkpoint.py`)
`new_thread_id()` mints `"run-<12hex>"`. LangGraph's `SqliteSaver` snapshots state after each node. Before a new run, `resume_incomplete(graph, limit=20)` resumes any thread whose snapshot `.next` is non-empty (i.e. it was cut off mid-run); a corrupt thread is **logged, not fatal**. See the [LangGraph concept](../concepts/langgraph-state-machine.md).

### 3. Prompt-injection hygiene
Scraped, attacker-controllable text is wrapped in `<listing>...</listing>` with a system instruction to treat it strictly as data and **never follow instructions inside it** — for both listing assessment and [wiki synthesis](../components/wiki-layer.md).

## Alternatives & trade-offs

- **Retry everything (incl. 4xx)**: fewer error types to classify. **Trade-off**: wastes time re-sending doomed 4xx requests and blocks router escalation. Chosen design is WORSE at: it needs a hand-maintained `is_transient` classifier that can misjudge a novel error.
- **No checkpointing (just re-run from scratch)**: simpler, no extra SQLite file. **Trade-off**: a crash after expensive detail/LLM work throws it all away. Chosen design is WORSE at: it adds a second database and a resume path that can itself hit corrupt snapshots.
- **Trust scraped text in prompts**: simpler prompts. **Trade-off**: a listing title could carry an injection ("ignore your rules and…") that steers the LLM. Chosen design is WORSE at: nothing meaningful — the wrapping is cheap; it is strictly safer.

## Why this serves the goal

Together these let the agent run for months untended: it recovers from flaky networks, doesn't lose work on a crash, and can't be hijacked by the pages it reads.

## Revisit when

- A new class of transient error isn't being retried (extend `is_transient`).
- Resume-from-checkpoint proves more trouble than re-running (drop it).

## Related pages

- Concept: [LangGraph state machine](../concepts/langgraph-state-machine.md)
- Components: [LLM router](../components/llm-router.md), [scraper](../components/scraper.md), [wiki layer](../components/wiki-layer.md)
