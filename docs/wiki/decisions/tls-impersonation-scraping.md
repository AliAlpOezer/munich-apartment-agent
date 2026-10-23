---
type: decision
title: TLS-impersonation scraping (curl-cffi) with Playwright as escalation
description: Fetch pages with a browser-mimicking HTTP client and fall back to a real headless browser only when that gets blocked.
resource: src/apartment_agent/sources/wg_gesucht.py
tags: [decision, scraping, curl-cffi, playwright, anti-bot]
timestamp: 2026-07-12T00:00:00Z
---

> **Superseded 2026-10-22** by [cloudflare-workers-hosting.md](cloudflare-workers-hosting.md): a plain fetch with browser headers got `200` from WG-Gesucht, and the Worker cannot run curl-cffi. Revisit with Cloudflare Browser Rendering if Worker egress gets blocked.

## Context

WG-Gesucht actively blocks bots. Plain HTTP requests (Python `requests`) get rejected because the server can tell from the **TLS handshake fingerprint** that they aren't a real browser. But driving a full browser for every page is slow and heavy.

## What we chose

**`curl_cffi` with `impersonate="chrome"`** as the primary client — it reproduces Chrome's TLS fingerprint so the request looks browser-originated. A **headless-Chromium Playwright** path is kept as an *escalation*, used only when `curl_cffi` fails **and** the optional `[browser]` extra is installed; otherwise the original error is re-raised.

## How it works (beginner-first)

`curl_cffi` is an HTTP client that borrows a real browser's TLS handshake, so from the server's side the connection is indistinguishable from Chrome. Requests are paced with a ~2.5s human-ish delay and wrapped in `@network_retry`. If a fetch still fails, and Playwright is installed, the code launches a real headless browser (sync API on worker threads) to render the page; if Playwright isn't installed, it re-raises so the failure is visible.

## Alternatives & trade-offs

- **Plain `requests`**: trivial and fast. **Trade-off**: reliably blocked by WG-Gesucht — a non-starter here.
- **Always use a headless browser (Playwright)**: highest fidelity, survives more anti-bot measures. **Trade-off**: heavy (a whole Chromium per fetch), slow, and a big dependency; wasteful when a lightweight impersonating request works.
- **Where the chosen design is WORSE**: `curl_cffi` impersonation is a **cat-and-mouse hack** — it can break when the site upgrades its detection, and it does **not** execute JavaScript, so JS-rendered content is invisible to it. An always-browser approach would be more robust to both. We accept fragility and a JS blind spot for speed and a light footprint, keeping the browser as a rarely-used safety net.

## Why this serves the goal

Fast, cheap fetches in the common case, with a heavier fallback available when needed — the right cost/robustness balance for a 3-hourly scrape.

## Revisit when

- Impersonation starts getting blocked routinely (promote Playwright to primary).
- WG-Gesucht moves listing data behind client-side JS (impersonation can't see it).

## Related pages

- Component: [scraper](../components/scraper.md)
- Related decision: [resilience & safety](resilience-and-safety.md)
