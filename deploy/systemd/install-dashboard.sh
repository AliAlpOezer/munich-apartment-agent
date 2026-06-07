#!/usr/bin/env bash
# Install the dashboard as a per-user systemd service (long-running web UI on :8000),
# reachable from your other Tailscale devices. Run on the box from the repo root.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PORT=8000

echo "Repo: $REPO_DIR"
cd "$REPO_DIR"

# 1. web deps (fastapi + uvicorn) into the existing venv
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
./.venv/bin/python -m pip install -e ".[web]"

# 2. .env present? (needs SUPABASE_* at least)
[[ -f .env ]] || echo "WARNING: no .env — copy .env.example to .env and fill SUPABASE_* first." >&2

# 3. install + enable the service
mkdir -p "$UNIT_DIR"
cp deploy/systemd/apartment-dashboard.service "$UNIT_DIR/"
loginctl enable-linger "$USER" 2>/dev/null || \
  echo "Could not enable linger; run: sudo loginctl enable-linger $USER"
systemctl --user daemon-reload
systemctl --user enable --now apartment-dashboard.service

# 4. how to reach it
host="$(hostname)"
echo
echo "Dashboard running on :$PORT"
echo "  From a Tailscale device:  http://$host:$PORT"
ip="$(tailscale ip -4 2>/dev/null | head -1 || true)"
[[ -n "$ip" ]] && echo "  Or by Tailscale IP:       http://$ip:$PORT"
echo "  HTTPS tailnet URL (optional):  tailscale serve --bg $PORT"
echo "  Logs:  journalctl --user -u apartment-dashboard -f"
