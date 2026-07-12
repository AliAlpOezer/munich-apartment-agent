---
type: component
title: Database (local SQLite)
description: A self-initializing SQLite store that dedups listings and records runs, notifications, feedback, and workflow state.
resource: src/apartment_agent/db/sqlite_client.py
tags: [component, database, sqlite, dedup]
timestamp: 2026-07-12T00:00:00Z
---

## What it does

Persists listings so the agent knows what it has already seen (dedup), and records run counters, sent notifications, user feedback, and bot state. **SQLite** is a database that lives entirely in a single file — no server process. See the [SQLite vs Supabase decision](../decisions/local-sqlite-vs-supabase.md).

## Where it lives

`src/apartment_agent/db/sqlite_client.py` — class `ListingsDB`.

## Interface / behaviour

- **Self-initializing**: creates its schema on first use.
- **WAL** (Write-Ahead Logging) mode + `foreign_keys` on.
- **Short-lived connection per operation** — so the web thread and the run thread can both use it safely (thread-safe by construction).

## Tables

- `listings` — `UNIQUE(source, external_id)`; workflow columns `status` (default `'new'`), `status_updated_at`, `notified_at`, `first_seen_at`; plus indices. `price_listed` is **not** a column (it is transient).
- `runs` — counters + JSON `tokens` / `timings` / `error_detail`.
- `notifications` — `message_id` primary key → `(source, external_id)` (maps a Telegram message back to its listing for [feedback](notifications-and-feedback.md)).
- `feedback` — `sentiment` / `emoji` / `update_id`.
- `bot_state` — a simple key/value table (e.g. the Telegram update offset).

## The upsert invariant (important)

On re-scrape, the upsert **EXCLUDES** `status`, `status_updated_at`, and `notified_at`. So seeing the same listing again refreshes its data **without clobbering the workflow state** — a listing you already marked "seen" or already got notified about stays that way.

## Config / Settings keys that tune it

- `db_path` (default `apartments.sqlite`).
- Checkpoint DB is separate: `checkpoint_db` (`agent_state.sqlite`), used by LangGraph checkpointing.
- `*.sqlite` files are gitignored (single-box, no managed backups — a trade-off; see the decision).

## Related pages

- Decision: [local SQLite vs Supabase/managed Postgres](../decisions/local-sqlite-vs-supabase.md)
- Consumers: [notifications & feedback](notifications-and-feedback.md), [web dashboard](web-dashboard.md)
