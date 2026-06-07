#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Random video shuffler for gridplayer.

Reads digits 1-6 from stdin. For each digit N, samples N videos
(without replacement) from the repo's videos/ directory and hands
the playlist to gridplayer via direct AF_UNIX socket IPC.

Lifecycle: shuffler always owns gridplayer. At startup, any existing
gridplayer is shut down; then the shuffler spawns its own copy
pointing at a temp settings.ini that disables the "save playlist?"
prompt. Both the settings file and per-press playlists live in a
single process-scoped TemporaryDirectory that is auto-cleaned on
exit. The user's real gridplayer settings.ini is never touched.

Override the gridplayer launch command via the GRIDPLAYER_CMD env
var (default: `gridplayer`). Example for running from source:
    GRIDPLAYER_CMD="uv run gridplayer" ./scripts/shuffler.py
"""

import json
import os
import random
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from multiprocessing import connection
from pathlib import Path

VIDEO_DIR = Path(__file__).resolve().parent.parent / "videos" / "mp4"
VIDEO_GLOBS = ("*.mp4", "*.mov")
VALID_DIGITS = frozenset({"1", "2", "3", "4", "5", "6"})
QUIT_TOKENS = frozenset({"q", "quit", "exit"})
PLAYLIST_PREFIX = "gridplayer-shuffler-"
GRIDPLAYER_SOCKET = Path.home() / "Library/Caches/gridplayer/gridplayer-fileopen.socket"
LAUNCH_WAIT_S = 30
LAUNCH_POLL_S = 0.2
KILL_WAIT_S = 5

# gridplayer aspect modes: "fit" (letterbox, default), "stretch" (distort
# to fill), "none" (native size), "fill" (cover — smallest dim fits, larger
# overflows and clips, preserves aspect, no distortion).
VIDEO_ASPECT_MODE = "fill"


def discover_videos(directory: Path) -> list[Path]:
    """List video files (.mp4, .mov) in directory, sorted by name.

    Raises FileNotFoundError if the directory is missing,
    ValueError if no video files are found or any entry is not a
    regular file.
    """
    if not directory.is_dir():
        raise FileNotFoundError(f"video directory not found: {directory}")
    videos = sorted(v for glob in VIDEO_GLOBS for v in directory.glob(glob))
    if not videos:
        raise ValueError(f"no video files {VIDEO_GLOBS} found in {directory}")
    for v in videos:
        if not v.is_file():
            raise ValueError(f"not a regular file: {v}")
    return videos


def parse_count(line: str) -> int | None:
    """Parse a single digit 1-6 from a line. Return None for anything else."""
    s = line.strip()
    if s in VALID_DIGITS:
        return int(s)
    return None


def is_quit(line: str) -> bool:
    """True if the line is a quit token (q / quit / exit, case-insensitive)."""
    return line.strip().lower() in QUIT_TOKENS


def sample_videos(
    videos: list[Path],
    n: int,
    rng: random.Random | None = None,
) -> list[Path]:
    """Sample n videos without replacement. Caller guarantees 1 <= n <= len(videos)."""
    sampler = rng or random
    return sampler.sample(videos, k=n)


def write_playlist(videos: list[Path], in_dir: Path) -> Path:
    """Write a minimal .gpls playlist into a fresh NamedTemporaryFile in in_dir.

    Uses .gpls (not raw video args) because gridplayer's process_arguments
    APPENDS raw video args to the running grid but REPLACES it for .gpls files.
    """
    video_params = json.dumps({"aspect_mode": VIDEO_ASPECT_MODE})
    lines: list[str] = ["#GRIDPLAYER"]
    lines.extend(f"#V{idx}:{video_params}" for idx in range(len(videos)))
    lines.extend(str(v) for v in videos)
    lines.append("")
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".gpls",
        prefix="playlist-",
        dir=in_dir,
        delete=False,
    ) as f:
        f.write("\n".join(lines))
        return Path(f.name)


def gridplayer_command() -> list[str]:
    """Resolve the gridplayer launch command from $GRIDPLAYER_CMD (default: `gridplayer`)."""
    raw = os.environ.get("GRIDPLAYER_CMD", "gridplayer")
    return shlex.split(raw)


def write_settings_ini(dest: Path) -> Path:
    """Write a minimal gridplayer settings.ini at dest with shuffler overrides.

    Only includes the keys the shuffler cares about; everything else falls
    through to gridplayer's compiled-in defaults.

      * `playlist/track_changes=false` — suppress "save playlist?" prompt
        on every swap.
      * `misc/overlay_disabled=true` — gridplayer's show_overlay() early-
        returns, so the progress bar / title / controls never appear.
      * `misc/loading_status_disabled=true` — gridplayer skips the initial
        VideoStatus.show(), so the "loading" gridplayer logo doesn't flash
        before VLC starts painting each pane. Error states still show.
      * `misc/keep_window_size=true` — gridplayer's restore_to_minimum
        early-returns on playlist close, so the window stays at its
        current size across swaps instead of shrinking to minimum.
    """
    dest.write_text(
        "[playlist]\ntrack_changes=false\n"
        "\n[misc]\n"
        "overlay_disabled=true\n"
        "loading_status_disabled=true\n"
        "keep_window_size=true\n",
        encoding="utf-8",
    )
    return dest


def find_socket_owner_pids(sock: Path = GRIDPLAYER_SOCKET) -> list[int]:
    """Return PIDs holding the gridplayer IPC socket open (via lsof)."""
    if not sock.exists():
        return []
    try:
        out = subprocess.check_output(
            ["lsof", "-t", str(sock)],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [int(p) for p in out.split() if p.strip().isdigit()]


def kill_existing_gridplayer(timeout_s: float = KILL_WAIT_S) -> None:
    """SIGTERM any process listening on gridplayer's socket; SIGKILL on timeout."""
    pids = find_socket_owner_pids()
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not socket_responsive():
            return
        time.sleep(LAUNCH_POLL_S)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def socket_responsive() -> bool:
    """True if something is currently listening on gridplayer's IPC socket."""
    try:
        client = connection.Client(str(GRIDPLAYER_SOCKET), "AF_UNIX")
    except (FileNotFoundError, ConnectionRefusedError):
        return False
    client.close()
    return True


def spawn_gridplayer(settings_path: Path | None = None) -> subprocess.Popen | None:
    """Spawn gridplayer detached. Returns the Popen handle, or None if launch failed.

    If settings_path is given, gridplayer reads it instead of the user's
    default settings.ini (via the GRIDPLAYER_SETTINGS_PATH env var).
    """
    cmd = gridplayer_command()
    env = dict(os.environ)
    if settings_path is not None:
        env["GRIDPLAYER_SETTINGS_PATH"] = str(settings_path)
    try:
        return subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
    except FileNotFoundError:
        print(
            f"error: {cmd[0]!r} not found on PATH; "
            f"install gridplayer or set GRIDPLAYER_CMD",
            file=sys.stderr,
        )
        return None


def wait_for_socket(
    proc: subprocess.Popen,
    timeout_s: float = LAUNCH_WAIT_S,
) -> bool:
    """Poll until gridplayer's socket accepts connections, or timeout/proc dies."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        if socket_responsive():
            return True
        time.sleep(LAUNCH_POLL_S)
    return False


def shutdown_gridplayer(proc: subprocess.Popen, *, timeout_s: float = 5) -> None:
    """Best-effort tear-down: SIGTERM, wait, SIGKILL fallback."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=timeout_s)


def hand_off(playlist_path: Path) -> bool:
    """Send the playlist path to the running gridplayer via its IPC socket.

    Returns True on success. False if the socket disappeared mid-session.
    """
    try:
        client = connection.Client(str(GRIDPLAYER_SOCKET), "AF_UNIX")
    except (FileNotFoundError, ConnectionRefusedError):
        print(
            "error: gridplayer socket disappeared (window closed?); "
            "restart the shuffler",
            file=sys.stderr,
        )
        return False
    try:
        client.send([str(playlist_path)])
    finally:
        client.close()
    return True


def print_banner(videos: list[Path]) -> None:
    print(f"Loaded {len(videos)} videos from {VIDEO_DIR}:")
    for v in videos:
        print(f"  {v.name}")
    print()
    print("Press 1-6 + Enter to load N random videos. Ctrl-D (or 'q') to exit.")


def _run_loop(videos: list[Path], tmpdir: Path) -> None:
    for line in sys.stdin:
        if is_quit(line):
            return
        n = parse_count(line)
        if n is None:
            if line.strip():
                print(
                    "invalid input: expected 1-6 (or 'q' to quit)",
                    file=sys.stderr,
                )
            continue
        if n > len(videos):
            print(
                f"only {len(videos)} video(s) available",
                file=sys.stderr,
            )
            continue
        chosen = sample_videos(videos, n)
        playlist_path = write_playlist(chosen, tmpdir)
        if hand_off(playlist_path):
            print(f"loaded {n} video(s)")


def main() -> int:
    try:
        videos = discover_videos(VIDEO_DIR)
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix=PLAYLIST_PREFIX) as tmpdir:
        tmpdir_path = Path(tmpdir)
        settings_path = write_settings_ini(tmpdir_path / "settings.ini")

        if socket_responsive():
            print("an existing gridplayer is running; replacing it...", file=sys.stderr)
            kill_existing_gridplayer()

        print("starting gridplayer...", file=sys.stderr)
        owned_proc = spawn_gridplayer(settings_path)
        if owned_proc is None:
            return 1
        if not wait_for_socket(owned_proc):
            print(
                f"error: gridplayer didn't come up within {LAUNCH_WAIT_S}s",
                file=sys.stderr,
            )
            shutdown_gridplayer(owned_proc)
            return 1

        try:
            print_banner(videos)
            try:
                _run_loop(videos, tmpdir_path)
            except KeyboardInterrupt:
                pass
        finally:
            print("stopping gridplayer...", file=sys.stderr)
            shutdown_gridplayer(owned_proc)
    print("bye")
    return 0


if __name__ == "__main__":
    sys.exit(main())
