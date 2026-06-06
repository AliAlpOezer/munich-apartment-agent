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
   START → scrape → filter → dedup ──(new?)──► enrich → persist → notify → END
   (curl-cffi)   (warm≤700, (Supabase)        (LLM     (Supabase) (Telegram)
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

## Filters (configurable in `.env`)
- Warmmiete **≤ 700 €** (falls back to Kaltmiete when warm is unknown)
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
python -m apartment_agent.main             # full run: dedup, enrich, persist, notify
pytest                                     # unit tests (filter + parser), no creds needed
```

## Deploy (every 3 hours)
```bash
bash deploy/systemd/install.sh             # installs a user systemd timer
systemctl --user list-timers               # verify next run
journalctl --user -u apartment-agent -f    # watch logs
```

## Disclaimer
Personal, low-frequency automation for my own apartment search; scraped data is not redistributed.
Scraping may conflict with a site's Terms of Service — use responsibly and gently.
