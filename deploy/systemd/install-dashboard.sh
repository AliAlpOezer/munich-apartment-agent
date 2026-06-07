#!/usr/bin/env bash
# Install the dashboard as a long-running systemd service (web UI on :8000), reachable from your
# other Tailscale devices. Run on the box from the repo root.
#   - run as root  -> installs a SYSTEM service (matches the agent's system timer)
#   - run as a user -> installs a per-user service (needs linger)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PORT=8000
UNIT=apartment-dashboard.service

echo "Repo: $REPO_DIR"
cd "$REPO_DIR"

# 1. venv + web deps (fastapi + uvicorn)
[[ -d .venv ]] || python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[web]"

# 2. .env present? (needs SUPABASE_* at least)
[[ -f .env ]] || echo "WARNING: no .env — copy .env.example to .env and fill SUPABASE_* first." >&2

# 3. render the unit with absolute paths (no %h ambiguity)
render_unit() {  # $1 = WantedBy target
  cat <<EOF
[Unit]
Description=Munich apartment-hunter dashboard (web UI, reachable over Tailscale)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
Environment=CHECKPOINT_DB=$REPO_DIR/dashboard_state.sqlite
ExecStart=$REPO_DIR/.venv/bin/python -m apartment_agent.web --host 0.0.0.0 --port $PORT
Restart=on-failure
RestartSec=5
Nice=10

[Install]
WantedBy=$1
EOF
}

# 4. install + enable (system if root, else per-user)
if [[ "$(id -u)" -eq 0 ]]; then
  render_unit multi-user.target > "/etc/systemd/system/$UNIT"
  systemctl daemon-reload
  systemctl enable --now apartment-dashboard
  scope=system
else
  unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  mkdir -p "$unit_dir"
  render_unit default.target > "$unit_dir/$UNIT"
  loginctl enable-linger "$USER" 2>/dev/null || echo "run: sudo loginctl enable-linger $USER"
  systemctl --user daemon-reload
  systemctl --user enable --now apartment-dashboard
  scope=user
fi

# 5. how to reach it
echo
echo "Dashboard installed ($scope service) and running on :$PORT"
echo "  From a Tailscale device:  http://$(hostname):$PORT"
ip="$(tailscale ip -4 2>/dev/null | head -1 || true)"
[[ -n "$ip" ]] && echo "  Or by Tailscale IP:       http://$ip:$PORT"
echo "  HTTPS tailnet URL (optional):  tailscale serve --bg $PORT"
if [[ "$scope" == system ]]; then
  echo "  Logs:  journalctl -u apartment-dashboard -f"
else
  echo "  Logs:  journalctl --user -u apartment-dashboard -f"
fi
