from types import SimpleNamespace

import pytest

from gridplayer.params.static import VideoAspect, VideoCrop, VideoTransform
from gridplayer.vlc_player.player_base import VlcPlayerBase


class RecordingMediaPlayer:
    """Test double for the libvlc media player.

    Records ordered view-setter calls so tests can assert exactly which libvlc
    commands a view request issues, and prove that no setter runs synchronously
    on a callback thread.
    """

    def __init__(self, video_size: tuple[int, int] = (1920, 1080)) -> None:
        self._video_size = video_size
        self.calls: list[tuple[str, object]] = []

    def video_get_size(self, num: int = 0) -> tuple[int, int]:
        return self._video_size

    def video_set_aspect_ratio(self, aspect_ratio):
        self.calls.append(("aspect_ratio", aspect_ratio))

    def video_set_crop_geometry(self, crop_geometry):
        self.calls.append(("crop_geometry", crop_geometry))

    def video_set_scale(self, scale):
        self.calls.append(("scale", scale))


class _StubPlayer(VlcPlayerBase):
    """Minimal concrete VlcPlayerBase: stubs the abstract notify/loopback
    methods so the object constructs without a QThread or QApplication.
    """

    def notify_update_status(self, status, percent=0): ...
    def notify_error(self, error): ...
    def notify_time_changed(self, new_time): ...
    def notify_playback_status_changed(self, new_status): ...
    def notify_load_video_done(self, media_track): ...
    def notify_snapshot_taken(self, snapshot_path): ...
    def loopback_load_video_st2_set_media(self): ...
    def loopback_load_video_st3_extract_media_track(self): ...
    def loopback_load_video_st4_loaded(self): ...


def make_player(
    *,
    video_size: tuple[int, int] = (1920, 1080),
    pane_size: tuple[int, int] = (640, 360),
    aspect: VideoAspect = VideoAspect.FIT,
    scale: float = 1,
    crop: VideoCrop = VideoCrop(0, 0, 0, 0),
    transform: VideoTransform = VideoTransform.NONE,
    is_audio_only: bool = False,
    media: object | None = "__default__",
) -> _StubPlayer:
    player = _StubPlayer(vlc_instance=None)

    player._media_player = RecordingMediaPlayer(video_size=video_size)

    video = SimpleNamespace(
        aspect_mode=aspect,
        scale=scale,
        crop=crop,
        transform=transform,
    )
    player.media_input = SimpleNamespace(size=pane_size, video=video)

    if media == "__default__":
        media = SimpleNamespace(is_audio_only=is_audio_only)
    player.media = media

    return player


@pytest.fixture
def make_player_fixture():
    return make_player
