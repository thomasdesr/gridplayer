"""Tests for scripts/shuffler.py."""

import shutil
import random
import sys
import tempfile
from pathlib import Path

import pytest

# scripts/ isn't a package; add it to sys.path so we can import shuffler.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import shuffler  # noqa: E402


@pytest.fixture
def short_tmpdir():
    """Short tmp dir under /tmp — needed for AF_UNIX sockets (macOS ~104 char limit)."""
    d = Path(tempfile.mkdtemp(prefix="s", dir="/tmp"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------- parse_count ----------


@pytest.mark.parametrize(
    "line,expected",
    [
        ("1", 1),
        ("2", 2),
        ("3", 3),
        ("4", 4),
        ("5", 5),
        ("6", 6),
        (" 3 ", 3),
        ("\t4\n", 4),
    ],
)
def test_parse_count_valid(line, expected):
    assert shuffler.parse_count(line) == expected


@pytest.mark.parametrize(
    "line",
    ["", "  ", "0", "7", "12", "a", "1a", "1 2", "q", "quit", "\n"],
)
def test_parse_count_invalid(line):
    assert shuffler.parse_count(line) is None


# ---------- is_quit ----------


@pytest.mark.parametrize(
    "line",
    ["q", "Q", "quit", "QUIT", "Quit", "exit", "Exit", "  q  ", "\tquit\n"],
)
def test_is_quit_yes(line):
    assert shuffler.is_quit(line)


@pytest.mark.parametrize(
    "line",
    ["", "1", "qu", "exiting", "hello", "q1", "1q"],
)
def test_is_quit_no(line):
    assert not shuffler.is_quit(line)


# ---------- sample_videos ----------


@pytest.fixture
def video_pool():
    return [Path(f"/tmp/v{i}.mp4") for i in range(6)]


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6])
def test_sample_videos_correct_count(video_pool, n):
    chosen = shuffler.sample_videos(video_pool, n)
    assert len(chosen) == n


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6])
def test_sample_videos_no_duplicates(video_pool, n):
    chosen = shuffler.sample_videos(video_pool, n)
    assert len(set(chosen)) == n


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6])
def test_sample_videos_subset_of_input(video_pool, n):
    chosen = shuffler.sample_videos(video_pool, n)
    assert all(v in video_pool for v in chosen)


def test_sample_six_returns_all(video_pool):
    chosen = shuffler.sample_videos(video_pool, 6)
    assert set(chosen) == set(video_pool)


def test_sample_videos_uses_injected_rng(video_pool):
    # Same seeded Random -> same output, regardless of process-global state.
    a = shuffler.sample_videos(video_pool, 3, rng=random.Random(0))
    b = shuffler.sample_videos(video_pool, 3, rng=random.Random(0))
    assert a == b


def test_sample_videos_does_not_mutate_input(video_pool):
    before = list(video_pool)
    shuffler.sample_videos(video_pool, 4)
    assert video_pool == before


# ---------- discover_videos ----------


def _make_mp4s(directory: Path, count: int) -> None:
    for i in range(count):
        (directory / f"v{i}.mp4").write_bytes(b"")


def test_discover_videos_success(tmp_path):
    _make_mp4s(tmp_path, 6)
    videos = shuffler.discover_videos(tmp_path)
    assert len(videos) == 6
    assert all(v.suffix == ".mp4" for v in videos)
    assert videos == sorted(videos)  # output is sorted


def test_discover_videos_any_count(tmp_path):
    _make_mp4s(tmp_path, 3)
    assert len(shuffler.discover_videos(tmp_path)) == 3


def test_discover_videos_includes_mov(tmp_path):
    _make_mp4s(tmp_path, 2)
    (tmp_path / "clip.mov").write_bytes(b"")
    videos = shuffler.discover_videos(tmp_path)
    assert {v.suffix for v in videos} == {".mp4", ".mov"}
    assert len(videos) == 3
    assert videos == sorted(videos)  # output is sorted across extensions


def test_discover_videos_empty_raises(tmp_path):
    with pytest.raises(ValueError, match="no video files"):
        shuffler.discover_videos(tmp_path)


def test_discover_videos_missing_dir(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(FileNotFoundError):
        shuffler.discover_videos(missing)


def test_discover_videos_ignores_non_video(tmp_path):
    _make_mp4s(tmp_path, 6)
    (tmp_path / "thumb.jpg").write_bytes(b"")
    (tmp_path / "notes.txt").write_bytes(b"")
    videos = shuffler.discover_videos(tmp_path)
    assert len(videos) == 6


# ---------- _run_loop ----------


def test_run_loop_skips_count_over_pool(tmp_path, monkeypatch, capsys):
    import io

    videos = [Path(f"/tmp/v{i}.mp4") for i in range(2)]
    monkeypatch.setattr(sys, "stdin", io.StringIO("6\n"))
    monkeypatch.setattr(shuffler, "hand_off", lambda _p: pytest.fail("should not hand off"))
    shuffler._run_loop(videos, tmp_path)
    assert "only 2 video(s) available" in capsys.readouterr().err


def test_run_loop_hands_off_valid_count(tmp_path, monkeypatch):
    import io

    videos = [Path(f"/tmp/v{i}.mp4") for i in range(3)]
    monkeypatch.setattr(sys, "stdin", io.StringIO("2\n"))
    handed: list[Path] = []
    monkeypatch.setattr(shuffler, "hand_off", lambda p: handed.append(p) or True)
    shuffler._run_loop(videos, tmp_path)
    assert len(handed) == 1
    assert handed[0].suffix == ".gpls"


# ---------- write_playlist ----------


def test_write_playlist_writes_file(video_pool, tmp_path):
    result = shuffler.write_playlist(video_pool, tmp_path)
    assert result.exists()
    assert result.parent == tmp_path
    assert result.suffix == ".gpls"


def test_write_playlist_format(video_pool, tmp_path):
    import json as _json

    path = shuffler.write_playlist(video_pool[:3], tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "#GRIDPLAYER"
    v_lines = [l for l in lines if l.startswith("#V")]
    assert len(v_lines) == 3
    for idx, line in enumerate(v_lines):
        prefix = f"#V{idx}:"
        assert line.startswith(prefix)
        params = _json.loads(line[len(prefix) :])
        assert params["aspect_mode"] == shuffler.VIDEO_ASPECT_MODE
    uri_lines = [l for l in lines if l and not l.startswith("#")]
    assert uri_lines == [str(v) for v in video_pool[:3]]


def test_write_playlist_videos_parse_with_aspect_mode(video_pool, tmp_path):
    from gridplayer.models.playlist import Playlist

    path = shuffler.write_playlist(video_pool[:2], tmp_path)
    parsed = Playlist.read(path)
    assert len(parsed.videos) == 2
    for v in parsed.videos:
        assert v.aspect_mode.value == shuffler.VIDEO_ASPECT_MODE


def test_write_playlist_fresh_per_call(video_pool, tmp_path):
    a = shuffler.write_playlist(video_pool, tmp_path)
    b = shuffler.write_playlist(video_pool, tmp_path)
    assert a != b
    assert a.exists() and b.exists()


# ---------- hand_off ----------


def test_hand_off_fails_when_socket_missing(short_tmpdir, monkeypatch, capsys):
    monkeypatch.setattr(shuffler, "GRIDPLAYER_SOCKET", short_tmpdir / "nope.sock")
    assert shuffler.hand_off(short_tmpdir / "x.gpls") is False
    assert "socket disappeared" in capsys.readouterr().err


# ---------- socket_responsive / spawn / shutdown ----------


def test_socket_responsive_false_when_socket_missing(short_tmpdir, monkeypatch):
    monkeypatch.setattr(shuffler, "GRIDPLAYER_SOCKET", short_tmpdir / "nope.sock")
    assert shuffler.socket_responsive() is False


def test_socket_responsive_true_with_listener(short_tmpdir, monkeypatch):
    from multiprocessing import connection as mp_conn

    sock_path = short_tmpdir / "test.sock"
    monkeypatch.setattr(shuffler, "GRIDPLAYER_SOCKET", sock_path)
    listener = mp_conn.Listener(str(sock_path), "AF_UNIX")
    try:
        assert shuffler.socket_responsive() is True
    finally:
        listener.close()


def test_spawn_gridplayer_returns_none_when_cmd_missing(monkeypatch, capsys):
    monkeypatch.setenv("GRIDPLAYER_CMD", "/nonexistent/binary-not-real-xyzzy")
    result = shuffler.spawn_gridplayer()
    if result is not None:
        result.terminate()
        result.wait()
    assert result is None
    assert "not found on PATH" in capsys.readouterr().err


# ---------- write_settings_ini / spawn env var ----------


def test_write_settings_ini_overrides(tmp_path):
    import configparser

    ini = shuffler.write_settings_ini(tmp_path / "settings.ini")
    cp = configparser.ConfigParser()
    cp.read(ini, encoding="utf-8")
    assert cp.get("playlist", "track_changes") == "false"
    assert cp.get("misc", "overlay_disabled") == "true"
    assert cp.get("misc", "loading_status_disabled") == "true"
    assert cp.get("misc", "keep_window_size") == "true"


def test_spawn_gridplayer_passes_settings_path_in_env(monkeypatch, tmp_path):
    captured: dict[str, str | None] = {}

    class FakePopen:
        def __init__(self, *_args, env=None, **_kwargs):
            captured["GRIDPLAYER_SETTINGS_PATH"] = env.get("GRIDPLAYER_SETTINGS_PATH")

    monkeypatch.setattr(shuffler.subprocess, "Popen", FakePopen)
    monkeypatch.setenv("GRIDPLAYER_CMD", "irrelevant")
    settings_path = tmp_path / "settings.ini"
    shuffler.spawn_gridplayer(settings_path)
    assert captured["GRIDPLAYER_SETTINGS_PATH"] == str(settings_path)


def test_spawn_gridplayer_no_env_var_without_settings(monkeypatch):
    captured: dict[str, str | None] = {}

    class FakePopen:
        def __init__(self, *_args, env=None, **_kwargs):
            captured["GRIDPLAYER_SETTINGS_PATH"] = env.get("GRIDPLAYER_SETTINGS_PATH")

    monkeypatch.setattr(shuffler.subprocess, "Popen", FakePopen)
    monkeypatch.setenv("GRIDPLAYER_CMD", "irrelevant")
    monkeypatch.delenv("GRIDPLAYER_SETTINGS_PATH", raising=False)
    shuffler.spawn_gridplayer()
    assert captured["GRIDPLAYER_SETTINGS_PATH"] is None


def test_shutdown_gridplayer_terminates_process():
    import subprocess as _sp

    proc = _sp.Popen(
        ["sleep", "60"],
        stdout=_sp.DEVNULL,
        stderr=_sp.DEVNULL,
    )
    assert proc.poll() is None
    shuffler.shutdown_gridplayer(proc, timeout_s=2)
    assert proc.poll() is not None


def test_shutdown_gridplayer_handles_already_exited():
    import subprocess as _sp

    proc = _sp.Popen(["true"], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
    proc.wait()
    shuffler.shutdown_gridplayer(proc)


def test_gridplayer_command_default(monkeypatch):
    monkeypatch.delenv("GRIDPLAYER_CMD", raising=False)
    assert shuffler.gridplayer_command() == ["gridplayer"]


def test_gridplayer_command_override(monkeypatch):
    monkeypatch.setenv("GRIDPLAYER_CMD", "uv run gridplayer")
    assert shuffler.gridplayer_command() == ["uv", "run", "gridplayer"]


def test_hand_off_sends_path_to_socket(short_tmpdir, monkeypatch):
    import threading
    from multiprocessing import connection as mp_conn

    sock_path = short_tmpdir / "test.sock"
    monkeypatch.setattr(shuffler, "GRIDPLAYER_SOCKET", sock_path)
    listener = mp_conn.Listener(str(sock_path), "AF_UNIX")
    received: list[list[str]] = []

    def serve():
        client = listener.accept()
        try:
            received.append(client.recv())
        finally:
            client.close()

    server_thread = threading.Thread(target=serve, daemon=True)
    server_thread.start()
    try:
        result = shuffler.hand_off(Path("/tmp/x.gpls"))
        server_thread.join(timeout=2)
    finally:
        listener.close()

    assert result is True
    assert received == [["/tmp/x.gpls"]]
