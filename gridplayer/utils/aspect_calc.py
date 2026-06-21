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
    fill_anchor: tuple[float, float] = (0.5, 0.5),
) -> ViewCommands:
    if aspect == VideoAspect.FILL:
        vid_x, vid_y = video_dimensions
        # Centered cover-crop uses VLC's native crop RATIO ("w:h"): VLC centers
        # it and recomputes it on every vout reconfiguration, so it survives
        # resize for free. Also the fallback before the source size is known.
        if fill_anchor == (0.5, 0.5) or vid_x == 0 or vid_y == 0:
            return ViewCommands(
                aspect_ratio=None,
                crop_geometry="{}:{}".format(*size),
                scale=0,
            )
        # Off-center: an absolute "+L+T+R+B" crop. The pixel edges are derived
        # from the anchor FRACTION here, so re-running compute_view on every
        # resize re-fits the crop to the new pane aspect (the fraction is what
        # persists, not the pixels — a one-shot absolute crop collapsed on resize).
        crop_edges = fill_cover_crop(video_dimensions, size, fill_anchor)
        return ViewCommands(
            aspect_ratio=None,
            crop_geometry="+{}+{}+{}+{}".format(*crop_edges),
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


def fill_cover_crop(
    video_dimensions: tuple[int, int],
    size: tuple[int, int],
    anchor: tuple[float, float],
) -> VideoCrop:
    """Cover-crop the source to the pane aspect, positioned by anchor.

    Returns the largest sub-rectangle of the source that has the pane's aspect
    ratio, as per-edge pixel crops (Left, Top, Right, Bottom). anchor is a
    fraction in [0, 1] per axis (0.5 = centered, 0 = top/left, 1 = bottom/right).
    Exactly one axis is trimmed — the surplus one.
    """
    vid_x, vid_y = video_dimensions
    scr_x, scr_y = size
    anchor_x, anchor_y = anchor

    # Compare source vs pane aspect by cross-multiplication (integer-safe).
    if vid_x * scr_y > scr_x * vid_y:
        # Source wider than the pane: trim left/right, keep full height.
        kept_x = max(1, min(round(vid_y * scr_x / scr_y), vid_x))
        surplus = vid_x - kept_x
        left = min(max(round(anchor_x * surplus), 0), surplus)
        return VideoCrop(left, 0, surplus - left, 0)

    # Source taller than (or equal to) the pane: trim top/bottom.
    kept_y = max(1, min(round(vid_x * scr_y / scr_x), vid_y))
    surplus = vid_y - kept_y
    top = min(max(round(anchor_y * surplus), 0), surplus)
    return VideoCrop(0, top, 0, surplus - top)


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
