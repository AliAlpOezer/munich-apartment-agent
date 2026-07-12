---
type: decision
title: Local SQLite vs Supabase / managed Postgres
description: Store everything in a single local SQLite file instead of a hosted database.
resource: src/apartment_agent/db/sqlite_client.py
tags: [decision, database, sqlite, deployment]
timestamp: 2026-07-12T00:00:00Z
---

## Context

The agent needs to remember which listings it has seen (dedup), plus runs, notifications, and feedback. An earlier version used **Supabase** (hosted Postgres). The agent actually runs on one small Ubuntu box.

## What we chose

**Local SQLite** — a database that is just a file, read/written by Python's stdlib `sqlite3`. Supabase was **removed**. `*.sqlite` files are gitignored.

## How it works (beginner-first)

`ListingsDB` is self-initializing (creates its own schema), runs in **WAL** mode with `foreign_keys` on, and opens a **short-lived connection per operation** so the web thread and the run thread can both touch it safely. No server process, no network, no credentials. See the [database component](../components/database.md).

## Alternatives & trade-offs

- **Supabase / managed Postgres**: managed backups, a remote dashboard, concurrent multi-client access, easy horizontal reach. **Trade-off**: a network dependency and credentials for a single-box, single-writer workload; an external service that can be down or rate-limited; more moving parts than the job needs.
- **Where the chosen design is WORSE**: **no managed backups and single-box durability** — if the box's disk dies, the data is gone unless someone set up backups. There is also **no built-in remote access** to the data (you SSH to the box). We traded operational safety-nets and remote convenience for zero dependencies and zero cost.

## Why this serves the goal

For one box, one writer, and modest data, SQLite is the smallest thing that works — no ops, no credentials, no outages. Simplicity and self-containment beat managed features here.

## Revisit when

- Multiple machines or writers need the same data.
- Data loss would be costly enough to require managed backups / replication.

## Related pages

- Component: [database](../components/database.md)
