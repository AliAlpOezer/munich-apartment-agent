---
type: decision
title: One Cloudflare Worker (cron + queue + D1 + static dashboard) replaces the box
description: Why the agent moved from a Python/LangGraph systemd box to a single TypeScript Worker, and the invariants, seams and failure model of that design.
resource: worker/
tags: [decision, architecture, hosting, cloudflare]
timestamp: 2026-10-22T00:00:00Z
---

## Context

The box deploy ("alpiclawd", systemd timer + FastAPI dashboard) is gone, and by 2026-10-22 the
Python pipeline was broken in two independent ways: `selectolax` 1.0 removed the `selectolax.parser`
backend (test collection fails on import), and WG-Gesucht moved search cards to
`a.wgg-list-card[data-id]`, so the live parser returned 0 listings while reporting a normal run.
The search target also moved: the user studies at TUM Garching and may work at SAP Labs Munich
(Friedrich-Ludwig-Bauer-Str. 5, Garching), so the anchor is no longer Alte Heide. The user asked for
hosting "as a Cloudflare page" with no server to maintain.

Checked 2026-10-22: a plain HTTPS GET (no TLS impersonation) gets `200` from WG-Gesucht, which is
served by Apache with no bot wall; each search page embeds a `markers` JSON array with exact
`lat`/`lng` per offer.

## Goal

Show the user every WG-Gesucht room or flat with warm rent at most 650 EUR, available by the end
of January 2027 and at most a 30-minute e-bike ride from both TUM Garching and SAP Garching,
within about an hour of it being posted, on a private dashboard, with nothing to keep running.

Technology-independent core: *each qualifying listing is shown once, soon after posting, with the
facts needed to decide (warm rent, bike minutes, dates), and nothing that might qualify is dropped
without a recorded reason.*

## Invariants

1. **Decisions are code over stored facts.** Every verdict (`matched`/`rejected` plus reasons) is
   computed by the pure filter from columns stored on the listing row, so any verdict can be
   explained and replayed. No model sits in control flow.
2. **One row per listing, monotone stages.** `UNIQUE(source, external_id)` plus upserts; stage
   moves only `pending_detail -> matched|rejected`, guarded in the `UPDATE ... WHERE stage = ?`.
   Queue redelivery, overlapping runs and retries cannot duplicate or regress a listing.
3. **One writer per fact.** The pipeline writes listing facts and stage; only the API writes
   `triage` (the user's new/seen/interested/dismissed). Neither touches the other's columns.
4. **Unknown is kept, never silently dropped.** Missing rent/size/date or an unreachable router
   keeps the listing (bike time falls back to a flagged estimate).
5. **Success is observed.** A `200` search page that yields 0 parsed cards while the page still
   carries offer markers is recorded as a failed page ("layout changed?"), never as "0 new".
6. **Polite and private.** All outbound scraping runs through one queue consumer at concurrency 1,
   with a page cap per run and a server-side cooldown on manual runs. Lister names, photos and
   contact data are never parsed, stored or committed (test fixtures are anonymized).

## Components

| Module (`worker/src/`) | Owns | Changes when |
|---|---|---|
| `wggesucht.ts` | search URL, card + marker parsing, detail cost parsing | the site's HTML changes |
| `bike.ts` | Valhalla matrix client, haversine estimate fallback | the routing provider changes |
| `filter.ts` | pure match rules | the user's criteria change |
| `store.ts` + `migrations/` | D1 schema and every SQL statement | the data model changes |
| `pipeline.ts` | queue stage handlers (search page, detail) | the run shape changes |
| `api.ts` + `public/` | dashboard JSON API and static UI | the UI changes |
| `config.ts` | typed criteria from `wrangler.jsonc` vars | a knob is added |

They share one deploy because none has a separate scaling or trust need; the seams below are
module boundaries, not network hops.

## Seams

| Seam | Carrier | Contract | Failure / ordering |
|---|---|---|---|
| cron or `POST /api/run` -> pipeline | Queue `apartment-jobs` | `{kind:"search", runId, page}` | at-least-once; page handling is an idempotent upsert; `run_pages` PK `(run_id, page)` |
| search page -> detail | same queue | `{kind:"detail", runId, listingId}` | handler no-ops unless the row is still `pending_detail` |
| pipeline -> store | D1 | `listings`, `runs`, `run_pages` tables | D1 error throws, the queue retries with backoff |
| pipeline -> WG-Gesucht | HTTPS GET | HTML | non-2xx throws; after the last retry the page or detail is recorded failed |
| pipeline -> router | HTTPS POST `sources_to_targets` | listing->anchor seconds | any error -> haversine x 1.3 estimate, `bike_source = "estimate"` |
| dashboard -> API | `fetch` same origin | JSON, `X-API-Token` on writes | writes fail closed when `API_TOKEN` is unset |

Run counts are derived from the rows (`first_seen_run`, `last_seen_run`, `stage`), not
incremented counters, so a redelivered message cannot inflate them.

## Failure model

- **Search page fetch fails** -> queue retries (3 attempts, backoff); then the page row is `failed`
  and the run shows red on the dashboard.
- **Parse finds 0 cards on a page that still has offer markers** -> page `failed`, no retry
  (deterministic), so a layout change surfaces in the first run instead of silently.
- **Detail fetch fails after retries** -> final filter runs on the card price (permissive),
  `detail_status = "failed"`.
- **Router down or rate-limited** -> estimate, flagged in the UI.
- **Two runs overlap** -> serialized by queue concurrency 1; upserts make the overlap harmless.
- **Manual run spam** -> `POST /api/run` refuses within the cooldown after the last run started.

Autonomy: scraping and filtering are autonomous (read-only on the outside world, idempotent).
There is no outward action (the user chose dashboard-only, no Telegram), so there is no gate.

## Alternatives rejected

- **Keep Python on GitHub Actions cron + Cloudflare Pages UI.** Keeps LangGraph, but Actions cron
  runs late by 10-60 min, auto-disables after 60 days without commits, scrapes from Azure IPs, and
  needs two platforms and two deploys. The user chose the single-platform option.
- **Python Workers (Pyodide).** `curl-cffi`, `selectolax` and LangGraph's checkpoint serializer
  are native and have no Pyodide build; pure-Python HTML parsing would blow the 10 ms CPU budget.
- **Cloudflare Pages + Functions.** Pages Functions cannot run cron triggers, so a second Worker
  would be needed anyway; a Worker with static assets is one deploy.
- **LangGraph.js.** The graph was linear with one branch. The queue already gives durable stages,
  per-item retry and resume (what LangGraph checkpointing provided); a framework adds a dependency
  without a capability.
- **One invocation does the whole run.** Free plan: 10 ms CPU and 50 subrequests per invocation;
  one failing detail page would fail the run with no per-item retry. Splitting into queue messages
  keeps each step small and gives per-item retry. Revisit Workers Paid ($5/month, 30 s CPU) only if
  a single page parse exceeds the budget.
- **KV or Durable Objects instead of D1.** KV is eventually consistent with no uniqueness
  constraint; idempotency would become "careful" instead of structural. D1 keeps the SQL model
  the Python store already had.

## Revisit when

- WG-Gesucht starts blocking Cloudflare egress (then: Browser Rendering or a residential fetcher).
- Observability shows CPU-limit errors (`1102`) on the free plan.
- LLM fit ranking, the markdown wiki or feedback learning are ported (second pass).

## Related pages

- [bike-time-filter.md](bike-time-filter.md) - how "30 minutes by bike" is computed.
- [warmmiete-detail-fetch.md](warmmiete-detail-fetch.md) - still applies; ported to `wggesucht.ts`.
- [local-sqlite-vs-supabase.md](local-sqlite-vs-supabase.md) - superseded by D1 for hosting.
- [tls-impersonation-scraping.md](tls-impersonation-scraping.md) - superseded: plain fetch works as of 2026-10-22.
