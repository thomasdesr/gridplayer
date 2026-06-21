from math import gcd

import pytest
from hypothesis import given
from hypothesis import strategies as st

from gridplayer.params.static import VideoAspect, VideoCrop
from gridplayer.utils.aspect_calc import (
    ViewCommands,
    calc_crop,
    calc_resize_scale,
    compute_view,
)

NO_CROP = VideoCrop(0, 0, 0, 0)


# --- Example tests: exact ViewCommands per VideoAspect ---


def test_fill_640x360():
    cmds = compute_view(
        video_dimensions=(1920, 1080),
        size=(640, 360),
        aspect=VideoAspect.FILL,
        scale=1,
        crop=NO_CROP,
    )
    assert cmds == ViewCommands(aspect_ratio=None, crop_geometry="640:360", scale=0)


def test_fill_ignores_video_dimensions():
    # FILL uses the pane size for the crop ratio, not the source dimensions.
    cmds_a = compute_view((1920, 1080), (800, 600), VideoAspect.FILL, 1, NO_CROP)
    cmds_b = compute_view((640, 480), (800, 600), VideoAspect.FILL, 1, NO_CROP)
    assert cmds_a == cmds_b
    assert cmds_a == ViewCommands(aspect_ratio=None, crop_geometry="800:600", scale=0)


def test_fit_no_crop():
    cmds = compute_view((1920, 1080), (640, 360), VideoAspect.FIT, 1, NO_CROP)
    assert cmds == ViewCommands(
        aspect_ratio="1920:1080", crop_geometry="640:360", scale=0
    )


def test_stretch_no_crop():
    cmds = compute_view((1920, 1080), (640, 360), VideoAspect.STRETCH, 1, NO_CROP)
    assert cmds == ViewCommands(
        aspect_ratio="640:360", crop_geometry="640:360", scale=0
    )


def test_none_no_crop():
    cmds = compute_view((1920, 1080), (640, 360), VideoAspect.NONE, 1, NO_CROP)
    assert cmds == ViewCommands(
        aspect_ratio="1920:1080", crop_geometry="1920:1080", scale=0
    )


def test_fit_scaled_above_one():
    # scale > 1 produces a non-zero resize_scale via calc_resize_scale.
    cmds = compute_view((1920, 1080), (640, 360), VideoAspect.FIT, 2, NO_CROP)
    expected_scale = calc_resize_scale((1920, 1080), (640, 360), VideoAspect.FIT, 2)
    assert cmds.scale == expected_scale
    assert cmds.scale != 0


def test_non_fill_absolute_crop():
    # A non-zero VideoCrop switches crop_geometry to absolute "+x+y+w+h" form.
    crop = VideoCrop(10, 20, 30, 40)
    cmds = compute_view((1920, 1080), (640, 360), VideoAspect.FIT, 1, crop)
    assert cmds.crop_geometry == "+10+20+30+40"
    assert cmds.aspect_ratio == "1920:1080"


def test_fill_ignores_absolute_crop():
    # FILL always uses the pane-ratio crop, never the absolute crop box.
    crop = VideoCrop(10, 20, 30, 40)
    cmds = compute_view((1920, 1080), (640, 360), VideoAspect.FILL, 1, crop)
    assert cmds == ViewCommands(aspect_ratio=None, crop_geometry="640:360", scale=0)


# --- Switch-away-from-FILL invariant: no stale fill state leaks ---


@pytest.mark.parametrize(
    "aspect",
    [VideoAspect.FIT, VideoAspect.NONE, VideoAspect.STRETCH],
)
def test_switch_away_from_fill_is_stateless(aspect):
    video_dimensions = (1920, 1080)
    size = (640, 360)

    fill = compute_view(video_dimensions, size, VideoAspect.FILL, 1, NO_CROP)
    assert fill.aspect_ratio is None

    after = compute_view(video_dimensions, size, aspect, 1, NO_CROP)
    fresh = compute_view(video_dimensions, size, aspect, 1, NO_CROP)

    # Stateless: the result after FILL equals the result computed in isolation.
    assert after == fresh
    # No leaked FILL state: a real aspect ratio is restored.
    assert after.aspect_ratio is not None


# --- Rotation: video_dimensions already reflects the rotated source ---


def test_rotation_consistent_for_fit():
    # The caller supplies rotation-corrected video_dimensions; FIT mirrors them.
    portrait = compute_view((1080, 1920), (640, 360), VideoAspect.FIT, 1, NO_CROP)
    assert portrait.aspect_ratio == "1080:1920"


def test_rotation_does_not_affect_fill():
    # FILL uses pane size only, so a rotated source yields the same commands.
    landscape = compute_view((1920, 1080), (640, 360), VideoAspect.FILL, 1, NO_CROP)
    portrait = compute_view((1080, 1920), (640, 360), VideoAspect.FILL, 1, NO_CROP)
    assert landscape == portrait


# --- Property tests ---

positive_dim = st.integers(min_value=1, max_value=10000)
sizes = st.tuples(positive_dim, positive_dim)
video_dims = st.tuples(positive_dim, positive_dim)
scales = st.floats(
    min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False
)


@given(video_dimensions=video_dims, size=sizes, scale=scales)
def test_fill_invariants(video_dimensions, size, scale):
    cmds = compute_view(video_dimensions, size, VideoAspect.FILL, scale, NO_CROP)

    assert cmds.aspect_ratio is None
    assert cmds.scale == 0
    assert cmds.crop_geometry == "{}:{}".format(*size)


@given(video_dimensions=video_dims, size=sizes, scale=scales)
def test_fill_crop_geometry_is_pane_ratio(video_dimensions, size, scale):
    cmds = compute_view(video_dimensions, size, VideoAspect.FILL, scale, NO_CROP)

    w_str, h_str = cmds.crop_geometry.split(":")
    w, h = int(w_str), int(h_str)
    # The crop_geometry encodes the pane size verbatim, whose reduced ratio
    # matches the reduced ratio of size.
    g = gcd(*size)
    assert (w // gcd(w, h), h // gcd(w, h)) == (size[0] // g, size[1] // g)


non_fill_aspects = st.sampled_from(
    [VideoAspect.FIT, VideoAspect.NONE, VideoAspect.STRETCH]
)


@given(
    video_dimensions=video_dims,
    size=sizes,
    aspect=non_fill_aspects,
    scale=scales,
)
def test_non_fill_matches_pure_helpers(video_dimensions, size, aspect, scale):
    cmds = compute_view(video_dimensions, size, aspect, scale, NO_CROP)

    crop_aspect, crop_geometry = calc_crop(video_dimensions, size, aspect)
    expected_scale = calc_resize_scale(video_dimensions, size, aspect, scale)

    assert cmds.aspect_ratio == "{}:{}".format(*crop_aspect)
    assert cmds.crop_geometry == "{}:{}".format(*crop_geometry)
    assert cmds.scale == expected_scale


@given(
    video_dimensions=video_dims,
    size=sizes,
    aspect=non_fill_aspects,
    crop=st.tuples(
        st.integers(min_value=1, max_value=999),
        st.integers(min_value=1, max_value=999),
        st.integers(min_value=1, max_value=999),
        st.integers(min_value=1, max_value=999),
    ).map(lambda c: VideoCrop(*c)),
)
def test_non_fill_absolute_crop_format(video_dimensions, size, aspect, crop):
    cmds = compute_view(video_dimensions, size, aspect, 1, crop)
    assert cmds.crop_geometry == "+{}+{}+{}+{}".format(*crop)
