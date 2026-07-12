---
type: decision
title: The LLM-wiki knowledge layer (compounding markdown)
description: Accumulate knowledge across runs in a markdown wiki, with code owning every number and the LLM owning only prose.
resource: src/apartment_agent/wiki/
tags: [decision, wiki, knowledge, llm, markdown]
timestamp: 2026-07-12T00:00:00Z
---

## Context

Each run scores listings in isolation. But useful knowledge — what a district is like, what the market looks like, what the user tends to prefer — only emerges *across* runs. Where should that live, and who is allowed to write the risky parts (the numbers)?

## What we chose

A **filesystem markdown wiki** that compounds over time (per-district pages, a market overview, a learned-preferences page), with a strict split: **code owns all statistics; the LLM owns only prose.** See the [wiki layer component](../components/wiki-layer.md).

## How it works (beginner-first)

Each page interleaves two section kinds marked by HTML comments:
- `<!-- auto:name -->` sections are regenerated deterministically by code (`stats_table`, `listing_line`) — **the LLM never writes a number**.
- `<!-- llm:synthesis -->` sections hold LLM prose, regenerated (tier `CHEAP→MEDIUM`) only when a router is available; on any failure the **prior prose is preserved**.

Because the markers delimit ownership, regenerating one kind can't corrupt the other. A separate `WikiLinter` reports broken links / orphans / stale / gaps but never auto-fixes.

## Alternatives & trade-offs

- **Stateless per-run scoring (no wiki)**: much simpler; nothing to maintain or lint. **Trade-off**: no compounding memory — the agent can't say "this district is usually pricey" because it never remembers.
- **Let the LLM author the whole page, numbers included**: fluent, less code. **Trade-off**: the LLM will hallucinate statistics; a made-up median rent is worse than none. The code-owns-numbers split exists precisely to make LLM-written pages trustworthy.
- **A structured DB of "insights" instead of markdown**: queryable, typed. **Trade-off**: markdown is human-readable, diffable in git, and doubles as documentation; a DB is not browsable at a glance.
- **Where the chosen design is WORSE**: it is **more machinery** (a store, page renderers, an ingestor, a linter, section-marker plumbing) than stateless scoring, and the markdown corpus can drift (stale pages, broken `[[wikilinks]]`) — which is why the linter exists. We accept more code and a maintenance surface to gain compounding, auditable, hallucination-safe knowledge.

## Why this serves the goal

Recommendations improve as context accumulates, and because numbers are code-owned the growing knowledge base stays trustworthy rather than becoming a pile of confident LLM guesses.

## Revisit when

- Wiki maintenance (staleness, broken links) outweighs the value of the accumulated knowledge.
- Insights need to be *queried* programmatically (consider a structured store alongside).

## Related pages

- Component: [wiki layer](../components/wiki-layer.md)
- Feeds: [human-in-the-loop feedback](human-in-the-loop-feedback.md) (preferences)
