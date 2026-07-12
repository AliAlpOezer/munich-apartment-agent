---
type: component
title: Notifications & feedback (Telegram)
description: Sends listing alerts and a per-run heartbeat over the Telegram Bot API, and ingests emoji reactions as preference signals.
resource: src/apartment_agent/notify/telegram.py
tags: [component, telegram, notifications, feedback, human-in-the-loop]
timestamp: 2026-07-12T00:00:00Z
---

## What it does

Delivers matched listings to the user on Telegram, sends a heartbeat when a run finds nothing, and turns the user's emoji **reactions** to those messages into thumbs-up/down preference signals fed back into the [wiki layer](wiki-layer.md).

No Telegram SDK is used — just `httpx` calls against the Bot API HTTP endpoints.

## Where it lives

- `src/apartment_agent/notify/telegram.py` — formatting + `TelegramNotifier`.
- `src/apartment_agent/feedback.py` — pure feedback logic.

## Interface

### telegram.py
- `format_listing(...)` — one listing, HTML-escaped.
- `format_digest(...)` — many listings; splits at Telegram's 4096-char message limit.
- `format_heartbeat(result)` (`telegram.py:62`) — e.g. `🟢 No new listings this run\nscraped 18 · matched 12 · 0 new`. See the [per-run heartbeat decision](../decisions/per-run-heartbeat.md).
- `TelegramNotifier.send(text) -> message_id?`, `.send_digest(...)`, `.send_per_listing(...)` (each per-listing message carries its `message_id` for reaction mapping), `.get_updates(allowed_updates=[message_reaction])`.

### feedback.py (pure, dependency-injected)
- `Reaction`, `PreferenceSignal` data types.
- Emoji whitelist: 👍 ❤️ 🔥 👌 🥰 = **+1**; 👎 💩 🤮 = **−1**.
- `sync_feedback(*, fetch_updates, resolve_listing, save_feedback, offset_get, offset_set) -> int` — all its I/O is injected as callables, so it is testable without Telegram or a DB. The **offset** advances to `max(update_id) + 1` for idempotency (each update is processed once).

## The notify node's choice

- **Feedback ON** → send **per-listing** messages (so each has its own `message_id` to react to).
- **Feedback OFF** → send one compact **digest**.

## Config / Settings keys that tune it

- `telegram_bot_token`, `telegram_chat_id` (empty → notifier disabled).
- `enable_feedback` (True) → per-listing vs digest, and whether reactions are ingested.

## Related pages

- Decision: [human-in-the-loop via Telegram reactions](../decisions/human-in-the-loop-feedback.md), [per-run heartbeat](../decisions/per-run-heartbeat.md)
- Feeds: [wiki layer](wiki-layer.md) (preferences fold into `auto:learned`)
- Maps via: [database](database.md) (`notifications` table)
