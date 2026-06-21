"""Off-center FILL anchor: anchored cover-crop via absolute edge geometry.

Centered FILL stays on the proven ratio-crop path; an off-center anchor
switches to an absolute "+L+T+R+B" crop whose pixel edges are recomputed from
the stored anchor FRACTION on every call, so it re-fits on pane resize.
"""

from hypothesis import given
from hypothesis import strategies as st

from gridplayer.params.static import VideoAspect, VideoCrop
from gridplayer.utils.aspect_calc import ViewCommands, compute_view, fill_cover_crop

CENTER = (0.5, 0.5)
NO_CROP = VideoCrop(0, 0, 0, 0)


# --- compute_view gating: centered vs off-center ---


def test_centered_fill_uses_ratio_crop():
    # Centered FILL keeps the proven ratio path (VLC centers it itself).
    cmds = compute_view((1920, 1080), (640, 360), VideoAspect.FILL, 1, NO_CROP, CENTER)
    assert cmds == ViewCommands(aspect_ratio=None, crop_geometry="640:360", scale=0)


def test_off_center_fill_uses_absolute_crop():
    cmds = compute_view(
        (1920, 1080), (640, 360), VideoAspect.FILL, 1, NO_CROP, (0.0, 0.5)
    )
    assert cmds.aspect_ratio is None
    assert cmds.scale == 0
    assert cmds.crop_geometry.startswith("+")


def test_off_center_falls_back_to_ratio_when_dims_unknown():
    # Source size not known yet (vout not up): cannot compute pixel crop.
    cmds = compute_view((0, 0), (640, 360), VideoAspect.FILL, 1, NO_CROP, (0.1, 0.9))
    assert cmds.crop_geometry == "640:360"


def test_default_anchor_is_centered():
    # Omitting fill_anchor must behave as centered (back-compat for callers).
    cmds = compute_view((1920, 1080), (640, 360), VideoAspect.FILL, 1, NO_CROP)
    assert cmds.crop_geometry == "640:360"


# --- fill_cover_crop geometry ---


def test_wide_source_crops_horizontally_only():
    # 1920x1080 source into a square pane: crop left/right, never top/bottom.
    crop = fill_cover_crop((1920, 1080), (500, 500), CENTER)
    assert crop.Top == 0 and crop.Bottom == 0
    assert crop.Left > 0 and crop.Right > 0


def test_tall_source_crops_vertically_only():
    # Portrait source into a wide pane: crop top/bottom only.
    crop = fill_cover_crop((1080, 1920), (640, 360), CENTER)
    assert crop.Left == 0 and crop.Right == 0
    assert crop.Top > 0 and crop.Bottom > 0


def test_anchor_zero_pins_to_left_edge():
    # anchor_x = 0 shows the leftmost region: nothing cropped from the left.
    crop = fill_cover_crop((1920, 1080), (500, 500), (0.0, 0.5))
    assert crop.Left == 0
    assert crop.Right > 0


def test_anchor_one_pins_to_right_edge():
    crop = fill_cover_crop((1920, 1080), (500, 500), (1.0, 0.5))
    assert crop.Right == 0
    assert crop.Left > 0


def test_center_anchor_is_symmetric():
    crop = fill_cover_crop((1920, 1080), (500, 500), CENTER)
    # Even split, within 1px rounding.
    assert abs(crop.Left - crop.Right) <= 1


# --- properties ---

dims = st.tuples(
    st.integers(min_value=1, max_value=10000), st.integers(min_value=1, max_value=10000)
)
fracs = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
anchors = st.tuples(fracs, fracs)


@given(video_dimensions=dims, size=dims, anchor=anchors)
def test_edges_non_negative_and_within_source(video_dimensions, size, anchor):
    crop = fill_cover_crop(video_dimensions, size, anchor)
    vid_w, vid_h = video_dimensions

    assert crop.Left >= 0 and crop.Top >= 0 and crop.Right >= 0 and crop.Bottom >= 0
    # Kept region stays inside the source and is non-empty on both axes.
    kept_w = vid_w - crop.Left - crop.Right
    kept_h = vid_h - crop.Top - crop.Bottom
    assert 0 < kept_w <= vid_w
    assert 0 < kept_h <= vid_h


@given(video_dimensions=dims, size=dims, anchor=anchors)
def test_only_one_axis_is_cropped(video_dimensions, size, anchor):
    # A cover-crop trims exactly one dimension (the surplus one), never both.
    crop = fill_cover_crop(video_dimensions, size, anchor)
    horizontal = crop.Left + crop.Right
    vertical = crop.Top + crop.Bottom
    assert horizontal == 0 or vertical == 0


# Realistic display/source sizes: pixel quantization stays small relative to
# the dimensions, so the aspect match is a meaningful (tight) check. At
# pathological aspect extremes integer rounding makes exact matching impossible.
sane_dims = st.tuples(
    st.integers(min_value=100, max_value=4000),
    st.integers(min_value=100, max_value=4000),
)


@given(video_dimensions=sane_dims, size=sane_dims, anchor=anchors)
def test_kept_region_matches_pane_aspect(video_dimensions, size, anchor):
    crop = fill_cover_crop(video_dimensions, size, anchor)
    vid_w, vid_h = video_dimensions
    pane_w, pane_h = size
    kept_w = vid_w - crop.Left - crop.Right
    kept_h = vid_h - crop.Top - crop.Bottom

    # kept_w / kept_h ~= pane_w / pane_h, checked by cross-multiplication. The
    # kept dimension is rounded to a pixel, so the error is bounded by one
    # pane-side worth of slack.
    lhs = kept_w * pane_h
    rhs = pane_w * kept_h
    assert abs(lhs - rhs) <= max(pane_w, pane_h) + 1


@given(anchor=anchors)
def test_compute_view_off_center_is_fill_invariant(anchor):
    if anchor == CENTER:
        return
    cmds = compute_view((1920, 1080), (640, 360), VideoAspect.FILL, 1, NO_CROP, anchor)
    assert cmds.aspect_ratio is None
    assert cmds.scale == 0
