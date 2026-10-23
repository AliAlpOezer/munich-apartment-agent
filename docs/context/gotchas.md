# Gotchas — munich-apartment-agent

### A run shows "failed: 0 cards parsed (N map markers)"
Cause: WG-Gesucht changed its card markup (it did in October 2026: cards became
`a.wgg-list-card[data-id]`). The pipeline records this as a failed page on purpose instead of
reporting "0 new".
Fix: update the selectors in `worker/src/wggesucht.ts` from a live page, refresh
`worker/test/fixtures/` (anonymize lister names, photos, initials), rerun `npm test`.

### Every ride on a run shows "ride estimated"
Cause: the Valhalla matrix request was refused. The FOSSGIS instance caps matrices at 100 source x
target pairs (HTTP 400, error_code 150); adding the 9 U6 stops made 20 x 11 = 220 pairs.
Fix: `bike.ts` chunks sources to `MAX_MATRIX_PAIRS / targets`. A router failure now shows as a note
in the run history, and estimated rides are re-routed on the next run. If it recurs, reproduce with
a direct `sources_to_targets` POST and read the error body.

### Map shows "API KEY REQUIRED" tiles
Cause: CARTO basemaps now require an API key.
Fix: the dashboard uses `tile.openstreetmap.org` and darkens it with a CSS filter in dark mode.
Don't switch tile providers without checking key requirements.

### Elements with the `hidden` attribute still show
Cause: any CSS `display` rule (e.g. `.badge { display: inline-flex }`) overrides `[hidden]`.
Fix: `worker/public/style.css` has `[hidden] { display: none !important; }`; keep it.

### Python tests fail on import: "Modest backend is deprecated since selectolax 1.0"
Cause: selectolax 1.0 removed `selectolax.parser`.
Fix: already moved to `selectolax.lexbor` (2026-10-22). Applies only to the retired Python code.

### wrangler on Windows ends with "Assertion failed: !(handle->flags & UV_HANDLE_CLOSING)" and exit 127
Cause: a libuv teardown crash in Node on Windows after wrangler has finished its work.
Fix: read the output, not the exit code (e.g. `wrangler types --check` printed "up to date" and
still exited 127). CI on Linux is unaffected.

### `@cloudflare/vitest-pool-workers` is deprecated
Cause: renamed to `@cloudflare/vitest-plugin` (`cloudflareTest()` Vite plugin, `cloudflare:workers`
for `env`/`exports`). Each plugin release pins an exact wrangler/miniflare version.
Fix: upgrade the plugin and wrangler together (2026-10-22 pair: plugin 1.4.0 + wrangler 4.149.0 +
vitest 4.1.12, chosen because older pairs carried sharp and vitest-mocker advisories).

## Legacy: Python box deploy (retired 2026-10-22)


### Editing a filter default in `config.py` (e.g. `move_in_date`) doesn't change deploy behaviour
Cause: `Settings` is pydantic-settings — for any key, a value set in the box's `.env` / real
environment always wins over the code default. The default in `config.py` is only used when the key
is absent from the environment entirely.
Fix: before "fixing" a filter value, check whether it's set in the deployed `.env` (SSH to the box
and grep it). If it is, edit `.env` there, not `config.py`. Full key list with defaults is in
`src/apartment_agent/config.py`'s `Settings` class.

### `date(2026, 09, 1)`-style literal crashes with `SyntaxError`
Cause: a leading-zero integer literal (`09`) is valid in JS/TS but a `SyntaxError` in Python 3 — a
trap specifically for developers coming from Node.
Fix: never write leading zeros in Python numeric literals; use `9` not `09`.
<!-- TODO(alp): docs/wiki/state/current-state.md attributes a prior fix to commit `2327809`, but
this repo's git history has only one commit (`b995c23`) — that hash is unverifiable; confirm or
drop it. -->

### Remote diagnostics over the box's Tailscale tunnel hang or drop
Cause: the box ("alpiclawd") is reached via local WSL → Tailscale → SSH, and that tunnel path has an
MTU black hole — packets roughly ≤1028 bytes pass, packets roughly ≥1228 bytes silently drop.
Fix: make remote commands trickle output line-by-line (avoid big single blobs of stdout/stderr) or
the session hangs.

### `https://alpiclawd.<tailnet>.ts.net/` dashboard URL is dead, `:8000` works
Cause: `tailscale serve` is proxying `/` to a stale/wrong port (18789) while the FastAPI app actually
listens on port 8000.
Fix: use `http://alpiclawd.<tailnet>.ts.net:8000/` (or the tailnet IP) directly until the `serve`
config is corrected.

### Scraper reports identical `scraped=18 / matched=12 / new=0` run after run
Cause: unconfirmed as of the last wiki pass — suspected stale/cached WG-Gesucht result set, not yet
diagnosed. Only became visible because of the per-run Telegram heartbeat (added specifically so
silent-but-alive runs are distinguishable from a dead agent).
Fix: not yet found. If investigating, check whether the scraper is genuinely hitting fresh pages
(response bodies/timestamps) vs. getting a cached/rate-limited response from WG-Gesucht.

<!-- TODO(alp): no gotchas confirmed beyond the 2026-07-12 wiki pass; verify against current
deployment state before relying on the last two entries. -->
