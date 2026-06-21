import logging
import random
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from pydantic import UUID4, BaseModel, Field, ValidationError, field_validator
from pydantic_extra_types.color import Color

from gridplayer.models.video_uri import AbsoluteFilePath, VideoURI, parse_uri
from gridplayer.params.static import (
    AudioChannelMode,
    VideoAspect,
    VideoCrop,
    VideoRepeat,
    VideoTransform,
)
from gridplayer.settings import Settings, default_field

MIN_SCALE = 1.0
MAX_SCALE = 10.0
MIN_RATE = 0.2
MAX_RATE = 12

FILL_ANCHOR_CENTER = (0.5, 0.5)


def _default_fill_anchor() -> tuple[float, float]:
    # A fresh random anchor per Video instance gives each pane a different
    # framing of the same source under FILL. Disable via the setting to pin
    # every pane to the centered cover-crop.
    if Settings().get("video_defaults/fill_random_anchor"):
        return (random.random(), random.random())
    return FILL_ANCHOR_CENTER


class Video(BaseModel):
    id: UUID4 = Field(default_factory=uuid4)
    uri: VideoURI

    # Presentation
    title: str | None = None
    color: Color = Color("white")

    # Seekable video
    current_position: int = 0
    loop_start: int | None = None
    loop_end: int | None = None

    repeat_mode: VideoRepeat = default_field("video_defaults/repeat")
    is_start_random: bool = default_field("video_defaults/random_loop")
    rate: Annotated[float, Field(ge=MIN_RATE, le=MAX_RATE)] = 1.0

    # Generic
    aspect_mode: VideoAspect = default_field("video_defaults/aspect")
    is_muted: bool = default_field("video_defaults/muted")
    is_paused: bool = default_field("video_defaults/paused")
    scale: Annotated[float, Field(ge=MIN_SCALE, le=MAX_SCALE)] = 1.0
    crop: VideoCrop = VideoCrop(0, 0, 0, 0)
    # FILL framing: fraction in [0, 1] per axis (0.5 = centered cover-crop).
    fill_anchor: tuple[float, float] = Field(default_factory=_default_fill_anchor)
    volume: float = 1.0
    transform: VideoTransform = default_field("video_defaults/transform")

    # Streamable
    stream_quality: str = default_field("video_defaults/stream_quality")
    auto_reload_timer_min: int = default_field("video_defaults/auto_reload_timer")

    # Tracks
    audio_track_id: int | None = None
    video_track_id: int | None = None

    audio_channel_mode: AudioChannelMode = default_field("video_defaults/audio_mode")

    @field_validator("fill_anchor")
    @classmethod
    def _clamp_fill_anchor(cls, value: tuple[float, float]) -> tuple[float, float]:
        x, y = value
        return (min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0))

    @property
    def uri_name(self) -> str:
        if isinstance(self.uri, Path):
            return self.uri.name

        return str(self.uri)

    @property
    def is_local_file(self):
        return isinstance(self.uri, AbsoluteFilePath)

    @property
    def is_http_url(self):
        return isinstance(self.uri, str) and self.uri.startswith(("http", "https"))


class VideoBlockMime(BaseModel):
    id: str
    video: Video


def filter_video_uris(uris: Iterable[str]) -> list[Video]:
    valid_urls = []

    for uri in uris:
        try:
            video = Video(uri=parse_uri(uri))
        except ValidationError as e:
            logging.getLogger("filter_video_uris").error(str(e))  # noqa: TRY400
            continue

        valid_urls.append(video)

    return valid_urls
