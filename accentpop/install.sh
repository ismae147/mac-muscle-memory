#!/usr/bin/env bash
# Install accentpop as a systemd --user service. No root, no system packages.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="$HOME/.local/share/accentpop"
UNIT_DIR="$HOME/.config/systemd/user"

if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
  echo "accentpop needs X11; this session is Wayland. Log in with 'GNOME on Xorg'." >&2
  exit 1
fi

echo "==> venv at $PREFIX/venv"
mkdir -p "$PREFIX" "$UNIT_DIR"
# --system-site-packages so the venv inherits the distro's PyGObject (GTK 3).
[ -d "$PREFIX/venv" ] || python3 -m venv --system-site-packages "$PREFIX/venv"
"$PREFIX/venv/bin/pip" install --quiet --upgrade python-xlib

echo "==> checking GTK 3 and Xlib"
"$PREFIX/venv/bin/python" - <<'PY'
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk          # noqa: F401
from Xlib.ext import record, xtest     # noqa: F401
print("    GTK 3 + Xlib RECORD/XTEST available")
PY

echo "==> linking daemon (edits in the repo take effect on restart)"
ln -sfn "$REPO/accentpop.py" "$PREFIX/accentpop.py"

echo "==> self-test"
"$PREFIX/venv/bin/python" "$PREFIX/accentpop.py" --selftest

echo "==> installing service"
install -m 644 "$REPO/accentpop.service" "$UNIT_DIR/accentpop.service"
# The user bus does not inherit DISPLAY/XAUTHORITY on its own.
systemctl --user import-environment DISPLAY XAUTHORITY
systemctl --user daemon-reload
systemctl --user enable --now accentpop.service
sleep 2

if systemctl --user is-active --quiet accentpop.service; then
  echo
  echo "accentpop is running. Hold 'a' in any text field for 300ms."
  journalctl --user -u accentpop.service -n 4 --no-pager -o cat | sed 's/^/    /'
else
  echo "accentpop failed to start:" >&2
  journalctl --user -u accentpop.service -n 20 --no-pager -o cat >&2
  exit 1
fi
