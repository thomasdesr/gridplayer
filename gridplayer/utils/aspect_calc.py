from gridplayer.params.static import VideoAspect, VideoCrop


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

    scaling = {
        VideoAspect.STRETCH: {"aspect": (scr_x, scr_y), "crop": (scr_x, scr_y)},
        VideoAspect.FIT: {"aspect": (vid_x, vid_y), "crop": (scr_x, scr_y)},
        VideoAspect.NONE: {"aspect": (vid_x, vid_y), "crop": (vid_x, vid_y)},
        # FILL: same defaults as FIT; the cover crop is applied as an absolute
        # crop_geometry by adjust_view, bypassing this aspect-only output.
        VideoAspect.FILL: {"aspect": (vid_x, vid_y), "crop": (scr_x, scr_y)},
    }

    return scaling[aspect]["aspect"], scaling[aspect]["crop"]


def calc_fill_crop(
    video_dimensions: tuple[int, int], size: tuple[int, int]
) -> VideoCrop:
    """Centered cover-crop of the source so its aspect matches the pane.

    Returns absolute (Left, Top, Right, Bottom) crop edges in source
    pixels, in the coordinate convention VLC's border-crop expects:
    Left/Top are offsets from the origin, Right/Bottom are absolute
    coordinates of the far edges (NOT margins). VLC clips Right to
    [Left+1, width], so passing the right margin here collapses the
    visible region to ~1px. After cropping, the source matches the pane
    aspect, so a fit-in-window scale fills the pane with no bars and no
    distortion.
    """
    vid_x, vid_y = video_dimensions
    scr_x, scr_y = size

    if vid_x == 0 or vid_y == 0 or scr_x == 0 or scr_y == 0:
        return VideoCrop(0, 0, 0, 0)

    vid_aspect = vid_x / vid_y
    pane_aspect = scr_x / scr_y

    if vid_aspect > pane_aspect:
        new_w = int(vid_y * pane_aspect)
        margin = (vid_x - new_w) // 2
        return VideoCrop(margin, 0, vid_x - margin, 0)

    new_h = int(vid_x / pane_aspect)
    margin = (vid_y - new_h) // 2
    return VideoCrop(0, margin, 0, vid_y - margin)
