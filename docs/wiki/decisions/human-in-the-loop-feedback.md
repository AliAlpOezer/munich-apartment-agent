---
type: decision
title: Human-in-the-loop via Telegram reactions
description: Learn the user's taste from emoji reactions on alert messages, rather than buttons, a web form, or no feedback at all.
resource: src/apartment_agent/feedback.py
tags: [decision, feedback, telegram, human-in-the-loop]
timestamp: 2026-07-12T00:00:00Z
---

## Context

The agent should get better at what the user likes over time, which needs a signal from the user. The user already receives every alert on Telegram. The cheapest possible signal is one the user gives without leaving that chat.

## What we chose

**Emoji reactions on the per-listing Telegram messages.** A whitelist maps reactions to sentiment — 👍 ❤️ 🔥 👌 🥰 = **+1**, 👎 💩 🤮 = **−1** — and those signals fold into the wiki's learned-preferences page. See [notifications & feedback](../components/notifications-and-feedback.md).

## How it works (beginner-first)

When feedback is on, each listing is sent as its **own** message carrying a `message_id` (stored in the `notifications` table). The bot polls `get_updates(allowed_updates=[message_reaction])`. `sync_feedback(...)` maps a reaction back to its listing via that `message_id`, records sentiment, and advances an **offset** to `max(update_id)+1` so each update is processed exactly once (idempotency). `sync_feedback` takes all its I/O as injected callables, so it's pure and testable. Signals feed the [wiki `auto:learned` section](../components/wiki-layer.md).

## Alternatives & trade-offs

- **Inline callback buttons** (tap a button under the message): explicit, unambiguous intent. **Trade-off**: more Bot API surface (callback queries, message editing), more UI to maintain; reactions are zero extra UI.
- **A web form / rating page**: richer feedback (free-text notes, multi-axis ratings). **Trade-off**: the user must leave Telegram and go somewhere — friction that means it rarely gets used.
- **No feedback**: simplest. **Trade-off**: the agent never learns; every run is stateless taste-wise.
- **Where the chosen design is WORSE**: reactions are a **coarse, low-bandwidth signal** — a single ±1 with no reason attached, and users react inconsistently. Buttons or a form would capture *why* a flat was liked. We trade signal richness for near-zero friction, betting that a signal actually given beats a richer one that isn't.

## Why this serves the goal

The best feedback mechanism is the one the user will actually use. A one-tap reaction in a chat they're already reading maximizes the odds of getting any signal at all.

## Revisit when

- Reaction signal proves too coarse to shift recommendations meaningfully (add buttons for a reason).
- The user wants to give structured notes (add a lightweight form).

## Related pages

- Component: [notifications & feedback](../components/notifications-and-feedback.md), [wiki layer](../components/wiki-layer.md)
