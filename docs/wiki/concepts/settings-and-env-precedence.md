---
type: concept
title: Settings and .env precedence (the move-in gotcha)
description: How pydantic-settings loads config, why .env beats the code default, and the deployment trap that follows from it.
resource: src/apartment_agent/config.py
tags: [config, pydantic-settings, env, deployment, beginner, gotcha]
timestamp: 2026-07-12T00:00:00Z
---

## What pydantic-settings is (one sentence)

**pydantic-settings** is a small library that builds a typed config object (`Settings`) by reading values from **environment variables and a `.env` file**, falling back to defaults you write in code.

If you come from Node: it is roughly `dotenv` + `zod` fused into one — it loads `.env` *and* validates/coerces types in a single declared class.

## The precedence rule (memorize this)

For any given key, the value is resolved in this order:

1. **`.env` file / real environment variable** — **wins if present**.
2. **Code default** — used only if the key is absent from the environment.

`extra="ignore"` means unknown keys in `.env` are silently dropped rather than erroring.

## The gotcha that will bite you

> **Editing a default in `config.py` does NOT change behaviour on the deployment box if that key is also set in the box's `.env`.**

Concrete example from this project: the code default for `move_in_date` is `2026-09-01`. The box `alpiclawd` has `MOVE_IN_DATE=...` set in its `.env`. So if you "fix" the move-in date by editing `config.py` and redeploy, **nothing changes** — the `.env` value still wins. You must edit the box's `.env`.

This is exactly the trap that makes config feel "haunted": the code says one thing, the running agent does another, and both are correct given the precedence rule.

### Checklist when changing a filter value

1. Is the key set in the box `.env`? If yes, edit `.env` there.
2. Is it set only in code? Then editing `config.py` is enough.
3. When in doubt, `grep` the deployed `.env` for the key before touching code.

## Related pages

- Component: [settings live inside orchestration](../components/orchestration.md) (full key list with defaults)
- State: [current state](../state/current-state.md) (the live filter values in force)
