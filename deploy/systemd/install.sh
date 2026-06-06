#!/usr/bin/env bash
# Install the apartment-agent as a per-user systemd timer (every 3h).
# Run on the target host (e.g. alpiclaw) from the repo root.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

echo "Repo:  $REPO_DIR"
cd "$REPO_DIR"

# 1. venv + deps
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e .

# 2. sanity: .env present?
if [[ ! -f .env ]]; then
  echo "WARNING: no .env found — copy .env.example to .env and fill it in before the first run." >&2
fi

# 3. install units (the units reference %h/munich-apartment-agent — symlink if repo lives elsewhere)
mkdir -p "$UNIT_DIR"
cp deploy/systemd/apartment-agent.service "$UNIT_DIR/"
cp deploy/systemd/apartment-agent.timer   "$UNIT_DIR/"
if [[ "$REPO_DIR" != "$HOME/munich-apartment-agent" ]]; then
  echo "NOTE: repo is not at \$HOME/munich-apartment-agent; either move it there or edit"
  echo "      WorkingDirectory/ExecStart in $UNIT_DIR/apartment-agent.service."
fi

# 4. allow user services to run without an active login session
loginctl enable-linger "$USER" 2>/dev/null || \
  echo "Could not enable linger automatically; run: sudo loginctl enable-linger $USER"

# 5. enable + start the timer
systemctl --user daemon-reload
systemctl --user enable --now apartment-agent.timer

echo
echo "Done. Inspect with:"
echo "  systemctl --user list-timers | grep apartment-agent"
echo "  systemctl --user start apartment-agent.service   # run once now"
echo "  journalctl --user -u apartment-agent -f"
