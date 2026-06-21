from gridplayer.params.static import VideoAspect, VideoCrop

NO_CROP = VideoCrop(0, 0, 0, 0)


def test_adjust_view_fill_issues_expected_commands(make_player_fixture):
    player = make_player_fixture(video_size=(1920, 1080), pane_size=(640, 360))

    player.adjust_view(
        size=(640, 360), aspect=VideoAspect.FILL, scale=1, crop=NO_CROP
    )

    assert player._media_player.calls == [
        ("aspect_ratio", None),
        ("crop_geometry", "640:360"),
        ("scale", 0),
    ]


def test_adjust_view_fit_issues_expected_commands(make_player_fixture):
    player = make_player_fixture(video_size=(1920, 1080), pane_size=(640, 360))

    player.adjust_view(
        size=(640, 360), aspect=VideoAspect.FIT, scale=1, crop=NO_CROP
    )

    assert player._media_player.calls == [
        ("aspect_ratio", "1920:1080"),
        ("crop_geometry", "640:360"),
        ("scale", 0),
    ]


def test_adjust_view_updates_pane_size_before_media_check(make_player_fixture):
    # media is None: adjust_view records the size but issues no libvlc commands.
    player = make_player_fixture(media=None)

    player.adjust_view(
        size=(800, 600), aspect=VideoAspect.FILL, scale=1, crop=NO_CROP
    )

    assert player.media_input.size == (800, 600)
    assert player._media_player.calls == []
