# Status — munich-apartment-agent

Last updated: 2026-07-21

## Current focus

<!-- TODO(alp): no in-flight branch/PR visible in this checkout — confirm current focus in-thread. -->

## In flight

<!-- none visible in this checkout -->

## Blocked

<!-- none confirmed -->

## Next up

<!-- TODO(alp): backlog not visible from repo state; ask in-thread or check GitHub issues. -->

## Recently landed

- `b995c23` docs: add project knowledge wiki at `docs/wiki/` (13 decisions, 9 components, 4 concepts,
  a state page, and an index — see `docs/wiki/index.md`).

As of the last wiki pass (2026-07-12): 93 tests passing / 1 skipped (live eval gated by
`RUN_LIVE_EVALS`); deployed on box "alpiclawd" as a systemd timer (`apartment-agent.timer`, every
~3h) plus a dashboard service on port 8000. Open items noted there: scraper returning identical
scraped=18/matched=12/new=0 counts for 18+ hours (unconfirmed, possibly stale WG-Gesucht results),
and a broken HTTPS dashboard proxy URL (Tailscale `serve` points `/` at a dead port; use `:8000`
directly). See `docs/wiki/state/current-state.md` for full detail if this task needs it — this
STATUS file is deliberately the short version.
