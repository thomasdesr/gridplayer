# pattern: Functional Core

from typing import NamedTuple

from gridplayer.params.static import VideoAspect, VideoCrop


class ViewCommands(NamedTuple):
    """The three libvlc view commands to issue for a given view request.

    aspect_ratio: argument for video_set_aspect_ratio; None disables forcing.
    crop_geometry: argument for video_set_crop_geometry ("w:h" ratio or
        "+x+y+w+h" absolute box).
    scale: argument for video_set_scale; 0 means fit-in-window.
    """

    aspect_ratio: str | None
    crop_geometry: str
    scale: float


def compute_view(
    video_dimensions: tuple[int, int],
    size: tuple[int, int],
    aspect: VideoAspect,
    scale: float,
    crop: VideoCrop,
) -> ViewCommands:
    if aspect == VideoAspect.FILL:
        # FILL cover-crops the source to the pane aspect via VLC's native crop
        # RATIO ("w:h"), at native aspect, fit-in-window. Uses the pane size,
        # not the source dimensions or the absolute crop box.
        return ViewCommands(
            aspect_ratio=None,
            crop_geometry="{}:{}".format(*size),
            scale=0,
        )

    crop_aspect, crop_geometry = calc_crop(video_dimensions, size, aspect)

    if crop == VideoCrop(0, 0, 0, 0):
        crop_geometry_fmt = "{}:{}".format(*crop_geometry)
    else:
        crop_geometry_fmt = "+{}+{}+{}+{}".format(*crop)

    resize_scale = calc_resize_scale(video_dimensions, size, aspect, scale)

    return ViewCommands(
        aspect_ratio="{}:{}".format(*crop_aspect),
        crop_geometry=crop_geometry_fmt,
        scale=resize_scale,
    )


def calc_resize_scale(
    video_dimensions: tuple[int, int],
    size: tuple[int, int],
    aspect: VideoAspect,
    scale: float,
) -> float:
    scr_x, scr_y = size
    vid_x, vid_y = video_dimensions

    if vid_x == 0 or vid_y == 0:
        return 0

    if scale > 1:
        if aspect == VideoAspect.FIT:
            resize_scale = max(scr_x / vid_x, scr_y / vid_y) * scale
        else:
            resize_scale = min(scr_x / vid_x, scr_y / vid_y) * scale

    else:
        resize_scale = 0

    return resize_scale


def calc_crop(
    video_dimensions: tuple[int, int], size: tuple[int, int], aspect: VideoAspect
):
    scr_x, scr_y = size
    vid_x, vid_y = video_dimensions

    # FILL is not handled here: compute_view applies its cover-crop via VLC's
    # native crop ratio and returns before reaching calc_crop.
    scaling = {
        VideoAspect.STRETCH: {"aspect": (scr_x, scr_y), "crop": (scr_x, scr_y)},
        VideoAspect.FIT: {"aspect": (vid_x, vid_y), "crop": (scr_x, scr_y)},
        VideoAspect.NONE: {"aspect": (vid_x, vid_y), "crop": (vid_x, vid_y)},
    }

    return scaling[aspect]["aspect"], scaling[aspect]["crop"]
