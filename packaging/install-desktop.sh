#!/usr/bin/env bash
# Install (or update) Gauntlet as a Linux desktop app.
#
# Keeps a dedicated clone of the repo in $GAUNTLET_APP_DIR, gives it its own venv with the
# remote-controller extras, and registers a "Gauntlet" entry in the desktop app menu.
# Re-run it any time to pull the latest main.
set -euo pipefail

REPO_URL="${GAUNTLET_REPO_URL:-https://github.com/ryanstephan42/gauntlet.git}"
BRANCH="${GAUNTLET_BRANCH:-main}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="${GAUNTLET_APP_DIR:-$DATA_HOME/gauntlet/app}"
APPS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"

if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
    git -C "$APP_DIR" checkout --quiet "$BRANCH"
    git -C "$APP_DIR" merge --quiet --ff-only "origin/$BRANCH"
else
    mkdir -p "$(dirname "$APP_DIR")"
    git clone --quiet --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

if command -v uv >/dev/null; then
    [ -x "$APP_DIR/.venv/bin/python" ] || uv venv --quiet "$APP_DIR/.venv"
    uv pip install --quiet --python "$APP_DIR/.venv/bin/python" -e "$APP_DIR[remote]"
else
    [ -x "$APP_DIR/.venv/bin/python" ] || python3 -m venv "$APP_DIR/.venv"
    "$APP_DIR/.venv/bin/pip" install --quiet -e "$APP_DIR[remote]"
fi

mkdir -p "$APPS_DIR" "$ICON_DIR"
install -m 644 "$APP_DIR/packaging/gauntlet.svg" "$ICON_DIR/gauntlet.svg"
cat > "$APPS_DIR/gauntlet.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Gauntlet
GenericName=Retro Game Gauntlet
Comment=Party challenges for RetroArch games, with remote controllers
Exec=env SDL_APP_ID=gauntlet $APP_DIR/.venv/bin/gauntlet
Path=$APP_DIR
Icon=gauntlet
Terminal=false
Categories=Game;
Keywords=retroarch;emulator;party;
StartupWMClass=gauntlet
EOF

if command -v update-desktop-database >/dev/null; then update-desktop-database "$APPS_DIR" || true; fi
if command -v gtk-update-icon-cache >/dev/null; then gtk-update-icon-cache -q "$DATA_HOME/icons/hicolor" 2>/dev/null || true; fi
echo "Gauntlet installed from $APP_DIR ($(git -C "$APP_DIR" rev-parse --short HEAD)); look for it in the app menu."
