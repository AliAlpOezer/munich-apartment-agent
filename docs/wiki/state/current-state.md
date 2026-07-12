---
type: state
title: Current state (2026-07-12)
description: What works now, what shipped this session, and the open questions — with verified numbers.
resource: null
tags: [state, status, deployment]
timestamp: 2026-07-12T00:00:00Z
---

## What works now (verified this session)

- **Tests**: **93 passed, 1 skipped** (`pytest`). The 1 skip is the live eval gated by the `RUN_LIVE_EVALS` env var — see [evals](../components/evals.md).
- **Commit count**: **30** commits (`git log --oneline | wc -l`).
- **Pipeline** end-to-end: scrape → filter → dedup → (detail → enrich → persist → wiki) → notify, skipping the middle when 0 new. See [orchestration](../components/orchestration.md).
- **Filter defaults in force**: warm-rent cap **657 €**, min size **10 m²**, move-in **2026-09-01**, listing types wg_room + apartment, **5 km radius around Alte Heide** (lat 48.1783353, lng 11.5978799), north Munich. (Live values come from the box `.env`, not the code default — see [settings & env precedence](../concepts/settings-and-env-precedence.md).)

## Deployment

- Runs on an Ubuntu box **"alpiclawd"** as two systemd units:
  - `apartment-agent.timer` → `apartment-agent.service` (oneshot, every ~3h).
  - `apartment-dashboard.service` (uvicorn, **port 8000**).
- The box is reachable only via a local WSL distro → **Tailscale** → SSH. That tunnel has an **MTU black hole**: packets ≤ ~1028 B pass, ≥ ~1228 B drop — so remote diagnostics must trickle output line-by-line or they hang.
- Dashboard on the tailnet: `http://alpiclawd.tail0f9474.ts.net:8000/` (or `http://100.85.197.19:8000/`).

## Shipped this session

1. **Per-run heartbeat** (commit `5a00008`) — an empty run now sends `🟢 No new listings this run / scraped.. · matched.. · ..new` so silence isn't mistaken for a dead agent. `format_heartbeat` in `notify/telegram.py`; `main()` uses `heartbeat_on_empty=True`; web "Search now" leaves it off. See the [decision](../decisions/per-run-heartbeat.md).
2. **Build-break fix** (commit `2327809`) — a prior commit wrote `date(2026, 09, 1)`; a leading-zero integer literal is a **SyntaxError in Python 3** (it's valid in JS/TS — the exact trap for a Node dev). Corrected to `date(2026, 9, 1)`; also updated two tests that hard-coded the old 12 m² / 2026-10-01 defaults.

## Done / in-progress / next

- **Done**: heartbeat, date-literal fix, radius search (657 € cap), placeholder-rent floor, Supabase → SQLite migration.
- **In progress**: monitoring whether the scraper is returning stale results (see open questions).
- **Next**: fix the broken HTTPS dashboard URL; investigate the constant scrape counts.

## Open questions

- **Stale/constant scrape counts**: the scraper has returned an identical **scraped=18 / matched=12 / new=0** on every run for **18+ hours** — possibly a stale/cached WG-Gesucht result set. **Unconfirmed.** (This is only *visible* thanks to the new [heartbeat](../decisions/per-run-heartbeat.md).)
- **Broken HTTPS dashboard URL**: the tidy `https://alpiclawd.tail0f9474.ts.net/` is broken — `tailscale serve` proxies `/` to a dead port **18789** while the app listens on **8000**. Open issue; use the `:8000` URL meanwhile. See [web dashboard](../components/web-dashboard.md).
- **Push status** (as of the digest, now resolved): the digest noted local `main` (`2327809`) was one commit ahead of `origin`; at documentation time `git log origin/main..HEAD` shows **0** commits ahead — the fix is pushed.

## Related pages

- All [decisions](../index.md#decisions), [components](../index.md#components), and [concepts](../index.md#concepts) — see the [index](../index.md).
