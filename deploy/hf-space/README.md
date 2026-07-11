---
title: Munich Apartment Agent
emoji: 🏠
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Munich Apartment Agent — dashboard

This HuggingFace Space runs the agent's FastAPI app (backend + dashboard) from the public repo
[AliAlpOezer/munich-apartment-agent](https://github.com/AliAlpOezer/munich-apartment-agent).
It shows matched listings, lets you mark each New / Seen / Sent, shows the last run report, and the
**Search now** button runs the agent in the Space. Data lives in a local SQLite file inside the Space
(`DB_PATH`) — see the persistence note below.

## Create the Space
1. New Space → **Docker** (blank) → set **visibility** (Private = only you, no token needed;
   Public = set `WEB_API_TOKEN` below).
2. Add the two files from `deploy/hf-space/` in the repo (`Dockerfile` and this `README.md`).
3. Set **Settings → Variables and secrets** (secrets, not plain vars, for keys):

| Secret | Needed | Notes |
|--------|--------|-------|
| `OPENROUTER_API_KEY` | for enrich/wiki | tier-1 free models; plus `TIER1_MODELS` if customised |
| `OPENCODE_ZEN_API_KEY` | optional | tier-2 escalation fallback (`TIER2_MODEL`) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | optional | notifications |
| `WEB_API_TOKEN` | if Space is **public** | guards every `/api`; enter it via the ⚙ button |
| `DB_PATH` | optional | SQLite path; point at attached persistent storage to survive restarts |
| `MOVE_IN_DATE`, `MAX_WARM_RENT_EUR`, … | optional | override search filters |

> **Persistence:** a free Space has ephemeral disk, so the SQLite DB (and its listings) resets on
> every restart. For durable data, attach [persistent storage](https://huggingface.co/docs/hub/spaces-storage)
> and set `DB_PATH` to a path under it — or run the whole thing on a persistent box (the recommended
> systemd/Tailscale path).

The Space builds, then serves on its URL. Open it; if you set `WEB_API_TOKEN`, click **⚙** and paste
it (stored only in your browser).

## Notes
- **Free Spaces sleep when idle** — the first visit after a nap cold-starts (~30s). A search runs on
  free CPU, so give it time.
- **Autonomous 3h runs**: the Space sleeps, so it won't self-run on a schedule. Keep those on the box
  (systemd timer) where the agent and dashboard share one SQLite file. (Since the DB is now local, a
  GitHub Actions cron writes its own throwaway DB unless you point `DB_PATH` at shared storage.)
- **Updating**: the image pins `AGENT_REF=main`; click **Factory rebuild** (or bump the build arg) to
  pull newer code from GitHub.
