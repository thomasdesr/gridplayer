import pytest

from gridplayer.params.static import VideoCrop
from gridplayer.utils.aspect_calc import calc_fill_crop

# VLC border-crop semantics (src/video_output/display.c):
#   Left/Top  -> offset from origin
#   Right/Bottom -> absolute coordinate of the far edge when > 0
#                   (a margin-from-edge only when <= 0)
# VLC then clips Right to [Left+1, width], so emitting the right *margin*
# here collapses the visible region to ~1px. These tests pin the absolute
# coordinate convention and the centered, no-distortion crop geometry.


def _visible(crop: VideoCrop, dims: tuple[int, int]) -> tuple[int, int]:
    """Visible (width, height) VLC derives from a border crop of `dims`."""
    vid_x, vid_y = dims
    right = crop.Right if crop.Right > 0 else vid_x + crop.Right
    bottom = crop.Bottom if crop.Bottom > 0 else vid_y + crop.Bottom
    return right - crop.Left, bottom - crop.Top


def test_fill_crop_landscape_into_portrait_pane_crops_sides():
    # 16:9 source, tall pane -> crop left/right, keep full height.
    crop = calc_fill_crop((1280, 720), (300, 600))
    assert crop.Top == 0  # full height
    assert crop.Bottom == 0
    assert crop.Left > 0  # sides trimmed
    assert crop.Right < 1280
    assert crop.Left == 1280 - crop.Right  # centered


def test_fill_crop_landscape_into_wide_pane_crops_top_bottom():
    # 16:9 source, very wide pane -> crop top/bottom, keep full width.
    crop = calc_fill_crop((720, 406), (320, 120))
    assert crop.Left == 0  # full width
    assert crop.Right == 0
    assert crop.Top > 0  # top/bottom trimmed
    assert crop.Bottom < 406
    assert crop.Top == 406 - crop.Bottom  # centered


def test_fill_crop_visible_region_matches_pane_aspect():
    # After cropping, the visible region must match the pane aspect so a
    # fit-scale fills with no distortion (within 1px integer rounding).
    dims, pane = (1280, 720), (391, 259)
    vis_w, vis_h = _visible(calc_fill_crop(dims, pane), dims)
    assert abs(vis_w / vis_h - pane[0] / pane[1]) < 0.01


def test_fill_crop_never_collapses_to_sliver():
    # The original bug: right/bottom emitted as margins -> VLC clips visible
    # to ~1px. Visible region must stay close to the full source on the
    # uncropped axis and a large fraction on the cropped axis.
    dims = (1280, 720)
    vis_w, vis_h = _visible(calc_fill_crop(dims, (391, 259)), dims)
    assert vis_h == 720  # uncropped axis untouched
    assert vis_w > 1000  # NOT collapsed to a sliver


def test_fill_crop_equal_aspect_is_noop():
    # Source already matches pane aspect -> no crop, full frame visible.
    dims = (1280, 720)
    vis_w, vis_h = _visible(calc_fill_crop(dims, (640, 360)), dims)
    assert (vis_w, vis_h) == (1280, 720)


@pytest.mark.parametrize(
    ("dims", "pane"),
    [((0, 0), (640, 360)), ((1280, 720), (0, 0)), ((1280, 0), (640, 360))],
)
def test_fill_crop_zero_dimensions_returns_no_crop(dims, pane):
    assert calc_fill_crop(dims, pane) == VideoCrop(0, 0, 0, 0)
