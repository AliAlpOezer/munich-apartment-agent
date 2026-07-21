# munich-apartment-agent

Autonomous LangGraph agent: scrapes Munich WG-Gesucht every ~3h, filters, dedups via local SQLite,
enriches via tiered LLM routing, maintains a markdown wiki, notifies via Telegram with
human-in-the-loop feedback.

Stack: Python 3.11+, LangGraph, pydantic-settings, curl-cffi (+Playwright), sqlite3, Telegram, FastAPI.
Slack channel: #proj-munich-apartment-agent

## Context protocol — follow this before doing anything else

1. Read `docs/context/INDEX.md` — a routing table to the one topic file matching your task.
2. Load **at most two** files from `docs/context/`. One is normal.
3. Do **not** glob, list, or bulk-read `docs/context/**`. Don't read a topic file "for
   background" — if INDEX.md didn't route you there, you don't need it.
4. If INDEX.md doesn't clearly route the task, read `docs/context/STATUS.md` only and
   proceed. Ask in-thread rather than reading more context.

Every `docs/context/` file is self-contained — none requires opening another one.

Deeper knowledge base: `docs/wiki/` — use `docs/context/` first.

## Ground rules

- Never add AI co-authorship trailers (`Co-Authored-By: Claude`, `Generated with…`) to commits
  or PR bodies.
- Branch before committing; never commit straight to the default branch.
- Update `docs/context/STATUS.md` in the same PR if project state changed.
