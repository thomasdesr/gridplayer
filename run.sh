#!/usr/bin/env bash
#
# run.sh: one-command launcher for the GridPlayer video-wall art piece.
#
# For a fresh Mac with nothing but the stock OS: clone the repo, install VLC,
# then run `./run.sh`. It bootstraps an isolated Python environment, installs
# GridPlayer, opens the player, and hands the terminal to the playlist
# controller. Type a button number and press Enter to show videos.
#
# Footprint: everything lives inside this repo folder (.uv/ and .venv/).
# Nothing touches your home directory or system. Delete the folder and no
# trace remains. No Xcode or compilers needed: every dependency is a wheel.

set -euo pipefail

# Repo root = the directory this script sits in, regardless of where it's run from.
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

# Pin every uv directory inside the repo so nothing leaks into $HOME.
export UV_PYTHON_INSTALL_DIR="$REPO_DIR/.uv/python"
export UV_CACHE_DIR="$REPO_DIR/.uv/cache"
UV_BIN_DIR="$REPO_DIR/.uv/bin"
UV="$UV_BIN_DIR/uv"

VLC_APP="/Applications/VLC.app"
CONTROLLER="$REPO_DIR/scripts/playlist_generator.py"

# 1. VLC is a native dependency (the video engine), not a pip package.
if [[ ! -d "$VLC_APP" ]]; then
  cat >&2 <<'EOF'
ERROR: VLC is required but was not found at /Applications/VLC.app

GridPlayer plays video through VLC's engine, which is a separate app:
  1. Download VLC for macOS from https://www.videolan.org/vlc/
  2. Drag VLC into your Applications folder
  3. Run this script again
EOF
  exit 1
fi

# 2. Fetch a self-contained uv (binary stays in the repo; no PATH/profile edits).
if [[ ! -x "$UV" ]]; then
  echo ">> Installing uv into .uv/bin ..."
  mkdir -p "$UV_BIN_DIR"
  # The installer may warn "uv ... shadowed by other commands in your PATH" if a
  # uv already exists on PATH. Harmless: run.sh always calls uv by absolute path.
  curl -LsSf https://astral.sh/uv/install.sh \
    | env UV_UNMANAGED_INSTALL="$UV_BIN_DIR" sh
fi

# 3. First run only: provision Python 3.13, create .venv, editable-install GridPlayer.
if [[ ! -d "$REPO_DIR/.venv" ]]; then
  echo ">> First-time setup: fetching Python 3.13 and installing GridPlayer ..."
  "$UV" sync --python 3.13 --no-dev
fi

# 4. Launch the player in the background, then hand stdin to the controller.
echo ">> Starting GridPlayer ..."
"$UV" run gridplayer &
PLAYER_PID=$!
trap 'kill "$PLAYER_PID" 2>/dev/null || true' EXIT INT TERM

# Wait for the single-instance socket so the first playlist actually lands.
SOCKET="${XDG_RUNTIME_DIR:-$HOME/Library/Caches}/gridplayer/gridplayer-fileopen.socket"
echo ">> Waiting for GridPlayer to come up ..."
for _ in $(seq 1 50); do
  [[ -S "$SOCKET" ]] && break
  sleep 0.2
done

echo ">> Ready. Type a button number and press Enter to show videos (Ctrl-C to quit)."
"$UV" run python "$CONTROLLER"
