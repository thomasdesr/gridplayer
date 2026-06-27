#!/usr/bin/env bash
# Launch GridPlayer and the playlist controller. Requires VLC.app.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

# Keep uv's Python, cache, and binary inside the repo (nothing leaks into $HOME).
export UV_PYTHON_INSTALL_DIR="$REPO_DIR/.uv/python"
export UV_CACHE_DIR="$REPO_DIR/.uv/cache"
UV="$REPO_DIR/.uv/bin/uv"

if [[ ! -d /Applications/VLC.app ]]; then
  echo "ERROR: VLC not found. Install it from https://www.videolan.org/vlc/" >&2
  exit 1
fi

if [[ ! -x "$UV" ]]; then
  echo ">> Installing uv ..."
  mkdir -p "$REPO_DIR/.uv/bin"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL="$REPO_DIR/.uv/bin" sh
fi

if [[ ! -d "$REPO_DIR/.venv" ]]; then
  echo ">> First-time setup ..."
  "$UV" sync --python 3.13 --no-dev
fi

# run.sh owns the gridplayer instance, so any left over sockets causes
# confusion for the playlist_generator. So rm it to ensure the file is what we
# expect and not a leaked one from a previous run
SOCKET="${XDG_RUNTIME_DIR:-$HOME/Library/Caches}/gridplayer/gridplayer-fileopen.socket"
rm -f "$SOCKET"

echo ">> Starting GridPlayer ..."
"$UV" run gridplayer &
PLAYER_PID=$!
trap 'kill "$PLAYER_PID" 2>/dev/null || true' EXIT INT TERM

echo ">> Waiting for GridPlayer to come up ..."
for _ in $(seq 1 100); do
  [[ -S "$SOCKET" ]] && break
  sleep 0.2
done
[[ -S "$SOCKET" ]] || echo ">> WARNING: GridPlayer socket never appeared; playlists may not load." >&2

echo ">> Ready. Type a button number and press Enter (Ctrl-C to quit)."
"$UV" run "$REPO_DIR/scripts/playlist_generator.py"
