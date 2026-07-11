# munich-apartment-agent

Autonomous LangGraph agent that scrapes Munich WG-Gesucht every ~3h, dedups via a local SQLite DB, enriches with tiered LLM usage, and notifies via Telegram. (Also known as 'munich-flat-search'.)

## Stack
Python / LangGraph + SQLite (stdlib `sqlite3`, self-initializing) + Telegram. Tier-1 LLM = OpenRouter free models.

## Repo
- git remote: https://github.com/AliAlpOezer/munich-apartment-agent.git

<!-- This file is this project's isolated context — a fresh agent opening this
     directory sees only this, not other projects. Add project-specific
     conventions, key commands, and gotchas here. -->
