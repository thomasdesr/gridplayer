import random, os
from glob import glob
from multiprocessing.connection import Client
from pathlib import Path
from pydantic.color import Color

from gridplayer.models.playlist import Playlist
from gridplayer.models.grid_state import GridState
from gridplayer.models.video import Video
from gridplayer.models.video_uri import AbsoluteFilePath
from gridplayer.params.static import GridMode, VideoAspect, VideoCrop, SeekSyncMode


print("Playlist Generator")
print("\n=== Start ===\n")

SCRIPT_DIR = Path(__file__).resolve().parent
files = glob(str(SCRIPT_DIR / "../videos/*"))


def path_files(files: list[str]):
    print("Pathing Files: " + str(files))

    return [Path(file).absolute() for file in files]


def build_playlist(filepaths: list[Path]) -> Playlist:
    print("\n=== Creating playlist ===")

    return Playlist(
        disable_click_pause=True,
        disable_wheel_seek=True,
        grid_state=GridState(mode=GridMode.AUTO_ROWS, is_fit=True, size=0),
        window_state=None,
        videos=[
            Video(
                # id=None,
                uri=AbsoluteFilePath(filepath),
                title=filepath.name,
                color="black",
                # current_position: int = 0,
                loop_start=None,
                loop_end=None,
                # is_start_random: bool = default_field("video_defaults/random_loop"),
                # rate: confloat(ge=MIN_RATE, le=MAX_RATE) = 1.0,
                aspect_mode=VideoAspect.FILL,
                # is_muted: bool = default_field("video_defaults/muted"),
                # is_paused: bool = default_field("video_defaults/paused"),
                # scale: confloat(ge=MIN_SCALE, le=MAX_SCALE) = 1.0,
                crop=VideoCrop(0, 0, 0, 0),
                # volume: float = 1.0,
                # transform: VideoTransform = default_field("video_defaults/transform"),
                # stream_quality: str = default_field("video_defaults/stream_quality"),
                # auto_reload_timer_min: int = default_field("video_defaults/auto_reload_timer"),
                audio_track_id=None,
                video_track_id=None,
                # audio_channel_mode: AudioChannelMode = default_field("video_defaults/audio_mode")
            )
            for filepath in filepaths
        ],
        snapshots=None,
        seek_sync_mode=SeekSyncMode.DISABLED,
    )


def mainLoop():
    num_files = 0
    while not num_files in range(1, len(files) + 1):
        try:
            num_files = int(input("Button number: "))
        except ValueError:
            continue

    print("You pressed button " + str(num_files))

    files_to_show = random.sample(files, num_files)

    print("Showing files " + str(files_to_show))

    random.shuffle(files_to_show)

    print("Randomized order: " + str(files_to_show))

    filepaths = path_files(files_to_show)

    playlist = build_playlist(filepaths)
    playlist_path = SCRIPT_DIR / "pl.gpls"
    playlist.save(playlist_path)

    print("Sending playlist to GridPlayer")

    try:
        socket_path = f"{os.environ.get('XDG_RUNTIME_DIR', Path.home() / 'Library/Caches')}/gridplayer/gridplayer-fileopen.socket"
        print("Socket path: ", socket_path)
        conn = Client(socket_path, "AF_UNIX")
        conn.send([str(playlist_path)])
        conn.close()
    except Exception as e:
        print("mError: ", repr(e))

    print("Sent files to GridPlayer")


while True:
    mainLoop()
