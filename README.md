# 🏠 Munich Apartment-Hunter Agent

An autonomous **LangGraph** agent that wakes every 3 hours, scrapes Munich housing listings
(WG-Gesucht first) against hard filters, deduplicates against a **Supabase** database, and pushes
new matches to **Telegram** — built to survive a brutally tight rental market where good listings
vanish within hours.

It also demonstrates **tiered LLM usage**: cheap models do the easy work, premium models are reserved
for the rare hard call — so you don't pay flagship prices to validate a JSON blob.

```
            systemd timer (every 3h, jittered)
                          │
   START → scrape → filter → dedup ──(new?)──► enrich → persist → wiki → notify → END
   (curl-cffi)   (warm≤700, (Supabase)        (LLM     (Supabase) (synth) (Telegram)
                  size≥12,                     fit-rank)
                  Oct-2026,
                  Munich+belt)
```

## Why it's interesting
- **Resilient scraping** — `curl-cffi` with Chrome TLS impersonation gets past the anti-bot layer
  that blocks plain `requests`; a Playwright-stealth fallback is wired for when it doesn't.
- **Source-adapter pattern** — adding ImmoScout24/Kleinanzeigen later is one subclass.
- **Tiered model router** — OpenRouter (free) → OpenCode Zen → Claude, escalating only on low
  confidence or failure, with intra-tier rotation for rate-limited free models.
- **Deterministic core, LLM at the edges** — parsing/filtering are pure and unit-tested; the LLM only
  ranks fit and writes one-line summaries, so the system is cheap, fast, and debuggable.
- **A knowledge wiki, not just a feed** — instead of scoring each listing in isolation and forgetting
  it, the agent maintains a synthesized, interlinked markdown wiki of the search (see below).

## Knowledge wiki (the *LLM Wiki* pattern)
Modelled on Karpathy's [*LLM Wiki*](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
idea: rather than re-deriving an answer from raw rows every time, the agent **incrementally maintains
a persistent, interlinked markdown wiki** on top of the listings data. Three layers — raw sources
(the `listings` table), the wiki (`WIKI_DIR`, default `./wiki`), and the schema
([`WIKI_SCHEMA.md`](WIKI_SCHEMA.md)) — and three operations:
- **Ingest** *(every run, in the `wiki` node)* — folds new listings into per-district pages and a
  market overview. Stats/links are computed deterministically; a cheap-tier model writes only the
  prose "market read", revising the prior text rather than restarting.
- **Query** — you (and a future frontend) read the synthesized wiki, not the raw rows.
- **Lint** *(`--lint`)* — health-checks the wiki for stale/orphan pages, gaps, and broken links.

The runtime wiki is **gitignored** so it persists across `git reset --hard` redeploys and never leaks
listing data into the repo; only the schema is tracked. Set `ENABLE_WIKI=false` to skip it.

## Filters (configurable in `.env`)
- Warmmiete **≤ 700 €** — the search card shows one ambiguous figure (usually Kaltmiete), so each
  new listing's detail page is fetched to resolve the real warm/cold split before the final filter
  (`ENABLE_DETAIL_FETCH`); falls back to the listed figure when a detail fetch is off or fails
- Size **≥ 12 m²**
- Available around **1 Oct 2026** (sublets ending before move-in are dropped)
- **WG rooms and apartments**, in **Munich + S-Bahn-commutable suburbs**

## Setup
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"            # add ".[browser]" for the Playwright fallback
cp .env.example .env               # then fill in keys
```
1. **Supabase** — create a project, run `src/apartment_agent/db/schema.sql`, put the URL + service key in `.env`.
2. **Telegram** — create a bot via @BotFather, get the token + your chat id.
3. **LLM keys** — OpenRouter (free tier), OpenCode Zen, Anthropic.

## Run
```bash
python -m apartment_agent.main --dry-run   # live scrape + filter, NO db/telegram, prints matches
python -m apartment_agent.main             # full run: dedup, enrich, persist, wiki, notify
python -m apartment_agent.main --lint      # health-check the knowledge wiki, write lint-report
python -m apartment_agent.main --sync-feedback   # pull Telegram 👍/👎 into learned preferences
python -m apartment_agent.evals.harness    # run fit-score evals against the live LLM tiers
pytest                                     # unit tests (no creds); RUN_LIVE_EVALS=1 adds a live eval
```

## Dashboard
A web frontend (FastAPI + a no-build vanilla-JS page) over the same Supabase data:
- listing **cards**, newest/new-status first (top-left); mark each **New / Seen / Sent**
- the agent's **last activity** time and a **run report** (new findings vs. only-already-seen vs.
  nothing matched)
- a **Search now** button and an **auto-search countdown** (`WEB_AUTO_SEARCH_MINUTES`) — both trigger
  a real agent run in the background; status polls live
```bash
pip install -e ".[web]"
python -m apartment_agent.web --host 0.0.0.0 --port 8000   # needs SUPABASE_* in .env
```

### Run on your own server over Tailscale (recommended)
Simplest and fullest: run the whole app on the box and reach it from your other Tailscale devices.
Same-origin (no CORS), and the tailnet is the access boundary (only your devices can reach it — no
token needed). Search-now, status edits, and the report all work.
```bash
bash deploy/systemd/install-dashboard.sh     # installs [web] deps + a user service on :8000
# then from any Tailscale device:
#   http://<box-hostname>:8000   (or http://<tailscale-ip>:8000)
# optional HTTPS tailnet URL:
tailscale serve --bg 8000                     # -> https://<box>.<tailnet>.ts.net
```
The autonomous 3h timer keeps running separately; the dashboard uses its own checkpoint DB so the
two never collide. (Set `WEB_AUTO_SEARCH_MINUTES=0` in `.env` if you don't want the open page to
auto-trigger extra runs.)

### Host the UI on GitHub Pages (backend stays on the box)
Pages serves only the static frontend; the FastAPI backend keeps running on the box. The page calls
the box's API, so the box must be reachable over **HTTPS** (a `https://<user>.github.io` page can't
call a plain-HTTP or private host — mixed content). [Tailscale Funnel](https://tailscale.com/kb/1223/funnel)
is the easy way to get an HTTPS URL.

1. **Expose the backend** (HTTPS), e.g. `tailscale funnel 8000`, and set in the box's `.env`:
   `WEB_API_TOKEN=<a long random secret>` and `WEB_CORS_ORIGINS=https://<user>.github.io`.
2. **Repo variable** `API_BASE` = the box's HTTPS URL (Settings → Actions → Variables).
3. Make the repo **public** (free Pages) and enable **Pages → Source: GitHub Actions**.
4. Push `main` — `.github/workflows/pages.yml` builds and deploys the static site.
5. Open the Pages URL, click **⚙**, and paste your `WEB_API_TOKEN`. The token lives only in your
   browser (localStorage) — it is **never** baked into the published page.

> The token guards every `/api` route, so a public Pages URL exposes nothing without it. Without a
> token the API is open — only acceptable on a private network.

### Or host the whole app free on HuggingFace Spaces
GitHub Pages can't run the backend, so "Search now" / status writes need a server. The simplest free
way to get the **full** app (UI + backend, same-origin, no box) is a HuggingFace **Docker Space**: it
`pip install`s this repo and runs the FastAPI app. See [`deploy/hf-space/`](deploy/hf-space/) for the
`Dockerfile`, the Space `README.md`, and setup (secrets + private/public choice). Autonomous 3h runs
still belong on the box or a GitHub Actions cron (free Spaces sleep when idle).

## Deploy (every 3 hours)
```bash
bash deploy/systemd/install.sh             # installs a user systemd timer
systemctl --user list-timers               # verify next run
journalctl --user -u apartment-agent -f    # watch logs
```

## Disclaimer
Personal, low-frequency automation for my own apartment search; scraped data is not redistributed.
Scraping may conflict with a site's Terms of Service — use responsibly and gently.
