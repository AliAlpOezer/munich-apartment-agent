---
type: decision
title: Per-run heartbeat on empty runs
description: Send a short "still alive, nothing new" Telegram message on every scheduled run that finds 0 new listings, so silence can't be mistaken for a dead agent.
resource: src/apartment_agent/notify/telegram.py
tags: [decision, notifications, telegram, observability, shipped-this-session]
timestamp: 2026-07-12T00:00:00Z
---

## Context

Most scheduled runs find nothing new. Before this change, such a run sent **nothing** — indistinguishable from a crashed agent, a broken bot token, or a scraper that silently stopped returning results. The user couldn't tell "quiet market" from "dead agent."

## What we chose

On every scheduled run that produced 0 new listings, send a compact heartbeat like:

```
🟢 No new listings this run
scraped 18 · matched 12 · 0 new
```

(or a ⚠️ variant if the run had errors). Shipped this session in commit `5a00008`.

## How it works (beginner-first)

`format_heartbeat(result)` (`telegram.py:62`) renders the line from the run's counters. `_run_graph` takes a `heartbeat_on_empty` flag; when set, not `dry_run`, a notifier exists, and `result.new == 0`, it sends the heartbeat (`main.py:98`). The **scheduled CLI** path calls `_run_graph(..., heartbeat_on_empty=True)` (`main.py:197`); the web **"Search now"** path leaves it off (a human is watching the dashboard, so a heartbeat would be noise).

## Alternatives & trade-offs

- **Silence on empty runs** (the old behaviour): zero notification noise. **Trade-off**: no liveness signal — a dead agent looks exactly like a quiet one, so failures go unnoticed for hours (indeed the [scraper's suspicious constant 18/12/0](../state/current-state.md) is only visible *because* of the heartbeat).
- **A once-daily digest instead of per-run**: far less chatter. **Trade-off**: up to ~24h of blindness — a mid-morning failure isn't visible until the next day's digest.
- **Where the chosen design is WORSE**: it is **chatty** — a message every ~3h even when nothing happens can train the user to tune the bot out (alert fatigue), which risks them missing a *real* listing alert buried among heartbeats. A digest would be quieter. We trade some noise for prompt, unambiguous liveness.

## Why this serves the goal

For an unattended long-running agent, "confirmed alive with nothing to report" is genuinely useful information. Positive confirmation each run is worth the extra chatter — and it's exactly what surfaced the stale-results anomaly.

## Revisit when

- Heartbeat chatter causes the user to mute the bot (switch to a digest or a health endpoint).
- A separate uptime monitor makes the per-run signal redundant.

## Related pages

- Component: [notifications & feedback](../components/notifications-and-feedback.md), [orchestration](../components/orchestration.md)
- State: [current state](../state/current-state.md)
