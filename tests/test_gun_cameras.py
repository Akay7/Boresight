"""The gun's camera sources, with no camera attached.

`rpicam` runs against a stand-in `rpicam-vid`: a small script that checks
the arguments it was given and writes frames, exactly as the real program
writes raw YUV420 to a pipe. `webcam` runs through OpenCV itself, with a
video file as the device.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from boresight.gun.app import Gun
from boresight.gun.cameras import (
    CameraError,
    RpicamCamera,
    WebcamCamera,
    choose_source,
    open_camera,
    rpicam_command,
)
from boresight.gun.config import (
    CAMERA_SOURCES,
    CameraConfig,
    ConfigError,
    GunConfig,
    Loaded,
    TuningConfig,
    parse_config,
)
from boresight.gun.fakes import RecordingSink, ScriptedTrigger
from boresight.gun.hid import HidGadgetBackend, pack_report
from boresight.gun.led import StatusIndicator
from boresight.inject import FakeCursorBackend
from boresight.marker_map import load_marker_map
from boresight.pipeline import DEFAULT_CONFIG_PATH, AimPipeline, replay

VIDEO = Path(__file__).parent / "fixtures" / "synthetic_video"

# --- choosing and configuring ---------------------------------------------


def test_the_source_defaults_to_auto() -> None:
    camera = parse_config({}).camera

    assert (camera.source, camera.device) == ("auto", 0)


def test_auto_is_rpicam_where_rpicam_vid_is_installed() -> None:
    assert choose_source("auto", lambda name: f"/usr/bin/{name}") == "rpicam"


def test_auto_is_a_webcam_elsewhere() -> None:
    assert choose_source("auto", lambda name: None) == "webcam"


@pytest.mark.parametrize("source", ["webcam", "rpicam", "picamera2"])
def test_an_explicit_source_is_kept(source) -> None:
    assert choose_source(source, lambda name: "/usr/bin/rpicam-vid") == source


def test_an_unknown_source_names_every_source() -> None:
    with pytest.raises(ConfigError) as raised:
        parse_config({"camera": {"source": "csi"}})

    assert all(source in str(raised.value) for source in CAMERA_SOURCES)


def test_a_webcam_device_can_be_a_path() -> None:
    camera = parse_config({"camera": {"source": "webcam", "device": "/dev/video2"}})

    assert camera.camera.device == "/dev/video2"


@pytest.mark.parametrize(("width", "height"), [(650, 480), (640, 470), (800, 600)])
def test_rpicam_refuses_a_size_it_would_pad(width, height) -> None:
    with pytest.raises(ConfigError) as raised:
        parse_config({"camera": {"source": "rpicam", "width": width, "height": height}})

    message = str(raised.value)
    assert f"{width}x{height}" in message and "multiple of 64" in message


@pytest.mark.parametrize(("width", "height"), [(640, 480), (1024, 768), (1280, 720)])
def test_rpicam_takes_unpadded_sizes(width, height) -> None:
    parse_config({"camera": {"source": "rpicam", "width": width, "height": height}})


def test_auto_on_a_pi_checks_the_size_when_it_opens() -> None:
    settings = CameraConfig(width=800, height=600)

    with pytest.raises(ConfigError, match="800x600"):
        open_camera(settings, which=lambda name: "/usr/bin/rpicam-vid")


# --- rpicam ---------------------------------------------------------------

STANDIN = """\
#!{python}
# A stand-in rpicam-vid: records its arguments, then behaves as STANDIN_MODE
# says, writing raw YUV420 frames from STANDIN_FRAMES to stdout.
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "args.json"), "w") as out:
    json.dump(sys.argv[1:], out)
mode = os.environ.get("STANDIN_MODE", "frames")
pace = float(os.environ.get("STANDIN_PACE_S", "0"))
if mode == "fail":
    sys.stderr.write("ERROR: *** no cameras available ***\\n")
    sys.exit(1)
data = open(os.environ["STANDIN_FRAMES"], "rb").read()
size = int(os.environ["STANDIN_FRAME_BYTES"])
frames = [data[i:i + size] for i in range(0, len(data), size)]
out = sys.stdout.buffer
if mode == "short":
    out.write(frames[0][: size // 2])
    out.flush()
    sys.exit(0)
while True:
    for frame in frames:
        out.write(frame)
        out.flush()
        if pace:
            time.sleep(pace)
    if mode != "forever":
        break
sys.stderr.write("stand-in done\\n")
"""


def _yuv420(luma: np.ndarray) -> bytes:
    height, width = luma.shape
    chroma = np.full(height * width // 2, 128, dtype=np.uint8)
    return luma.astype(np.uint8).tobytes() + chroma.tobytes()


@pytest.fixture
def standin(tmp_path, monkeypatch):
    """Install the stand-in; returns a function that loads it with frames."""
    if os.name != "posix":
        pytest.skip("the stand-in rpicam-vid is a shebang script")
    script = tmp_path / "rpicam-vid"
    script.write_text(STANDIN.format(python=sys.executable))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)

    def load(lumas: list[np.ndarray], mode: str = "frames", pace_s: float = 0.0):
        frames = tmp_path / "frames.yuv"
        frames.write_bytes(b"".join(_yuv420(luma) for luma in lumas))
        height, width = lumas[0].shape
        monkeypatch.setenv("STANDIN_FRAMES", str(frames))
        monkeypatch.setenv("STANDIN_FRAME_BYTES", str(width * height * 3 // 2))
        monkeypatch.setenv("STANDIN_MODE", mode)
        monkeypatch.setenv("STANDIN_PACE_S", str(pace_s))
        return str(script)

    load.args = lambda: json.loads((tmp_path / "args.json").read_text())
    return load


SMALL = CameraConfig(source="rpicam", width=64, height=32, fps=30, exposure_us=2500)


def _lumas(count: int, shape=(32, 64)) -> list[np.ndarray]:
    rng = np.random.default_rng(7)
    return [rng.integers(0, 256, shape, dtype=np.uint8) for _ in range(count)]


def test_the_command_fixes_exposure_gain_and_white_balance() -> None:
    command = rpicam_command(SMALL)

    def value(flag: str) -> str:
        return command[command.index(flag) + 1]

    assert command[0] == "rpicam-vid"
    assert value("--codec") == "yuv420" and value("--output") == "-"
    assert (value("--width"), value("--height"), value("--framerate")) == (
        "64",
        "32",
        "30",
    )
    assert value("--shutter") == "2500us" and value("--gain") == "1.0"
    assert value("--awbgains") == "1,1" and value("--denoise") == "off"
    assert value("--timeout") == "0" and "--nopreview" in command


def test_frames_come_back_as_their_luma_in_order(standin) -> None:
    lumas = _lumas(5)
    camera = RpicamCamera(SMALL, executable=standin(lumas))
    try:
        for expected in lumas:
            frame, sensor_s = camera.grab()
            np.testing.assert_array_equal(frame, expected)
            assert sensor_s is None
    finally:
        camera.close()
    assert standin.args() == rpicam_command(SMALL)[1:]


def test_rpicam_vid_failing_is_a_camera_error_with_its_words(standin) -> None:
    camera = RpicamCamera(SMALL, executable=standin(_lumas(1), mode="fail"))
    try:
        with pytest.raises(CameraError) as raised:
            camera.grab()
    finally:
        camera.close()

    assert "no cameras available" in str(raised.value)
    assert "exit code 1" in str(raised.value)


def test_a_short_frame_is_a_camera_error_not_a_misaligned_one(standin) -> None:
    camera = RpicamCamera(SMALL, executable=standin(_lumas(1), mode="short"))
    try:
        with pytest.raises(CameraError, match="mid-frame"):
            camera.grab()
    finally:
        camera.close()


def test_a_missing_rpicam_vid_is_explained(tmp_path) -> None:
    with pytest.raises(CameraError) as raised:
        RpicamCamera(SMALL, executable=str(tmp_path / "rpicam-vid"))

    assert "rpicam-apps" in str(raised.value) and "webcam" in str(raised.value)


def test_close_stops_a_running_rpicam_vid(standin) -> None:
    camera = RpicamCamera(SMALL, executable=standin(_lumas(2), mode="forever"))
    camera.grab()
    started = time.monotonic()

    camera.close()

    assert camera._process.poll() is not None
    assert time.monotonic() - started < 3


def test_the_gun_aims_from_rpicam_frames(standin) -> None:
    """End to end: the recorded video, as raw YUV420 from rpicam-vid,
    through the real gun loop, gives the server's positions."""
    manifest = json.loads((VIDEO / "manifest.json").read_text())
    lumas = [
        cv2.imread(str(VIDEO / entry["file"]), cv2.IMREAD_GRAYSCALE)
        for entry in manifest["frames"]
    ]
    settings = CameraConfig(source="rpicam", width=1280, height=720)
    camera = RpicamCamera(settings, executable=standin(lumas, pace_s=0.08))
    sink = RecordingSink()
    loaded = Loaded(
        GunConfig(camera=settings, tuning=TuningConfig(smoothing=False, hold_s=0.0)),
        load_marker_map(DEFAULT_CONFIG_PATH),
        None,
        None,
    )
    gun = Gun(
        loaded,
        camera,
        HidGadgetBackend(sink),
        ScriptedTrigger(),
        StatusIndicator(None),
    )

    # The stand-in exits after the last frame, which a live camera never
    # does: the gun reports it as a camera failure.
    assert gun.run(threading.Event()) == 1

    expected = {
        pack_report(*result.position, False)
        for result in replay(
            VIDEO,
            AimPipeline(load_marker_map(DEFAULT_CONFIG_PATH), FakeCursorBackend()),
        )
        if result.position is not None
    }
    assert len(sink.reports) >= len(expected) // 2
    assert set(sink.reports) <= expected


# --- webcam ---------------------------------------------------------------

LEVELS = [40, 80, 120, 160, 200]


@pytest.fixture
def video_file(tmp_path) -> Path:
    path = tmp_path / "webcam.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (320, 240))
    for level in LEVELS:
        writer.write(np.full((240, 320, 3), level, dtype=np.uint8))
    writer.release()
    assert path.stat().st_size > 0
    return path


def test_a_webcam_gives_greyscale_frames_in_order(video_file) -> None:
    camera = WebcamCamera(
        CameraConfig(source="webcam", device=str(video_file), width=320, height=240)
    )
    try:
        frames = []
        while (grabbed := camera.grab()) is not None:
            frames.append(grabbed[0])
    finally:
        camera.close()

    assert [frame.shape for frame in frames] == [(240, 320)] * len(LEVELS)
    assert [round(float(frame.mean()) / 40) * 40 for frame in frames] == LEVELS


def test_open_camera_picks_the_webcam_off_a_pi(video_file) -> None:
    settings = CameraConfig(device=str(video_file), width=320, height=240)

    camera = open_camera(settings, which=lambda name: None)
    try:
        assert isinstance(camera, WebcamCamera)
        assert camera.grab()[0].shape == (240, 320)
    finally:
        camera.close()


def test_a_webcam_that_will_not_open_is_explained() -> None:
    with pytest.raises(CameraError, match="cannot open camera"):
        WebcamCamera(CameraConfig(source="webcam", device="/nonexistent/video9"))


class StubCapture:
    """A webcam that keeps automatic exposure and then stops."""

    def __init__(self, device) -> None:
        self.set_calls: dict[int, float] = {}

    def isOpened(self) -> bool:  # noqa: N802 - OpenCV's name
        return True

    def set(self, prop: int, value: float) -> bool:
        self.set_calls[prop] = value
        return True

    def get(self, prop: int) -> float:
        return 3.0 if prop == cv2.CAP_PROP_AUTO_EXPOSURE else 0.0

    def read(self):
        return False, None

    def release(self) -> None:
        pass


def test_a_webcam_that_keeps_auto_exposure_is_warned_about(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="boresight.gun.cameras"):
        camera = WebcamCamera(
            CameraConfig(source="webcam", device=0, exposure_us=4000, gain=2.0),
            capture_factory=StubCapture,
        )

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "automatic exposure" in warnings[0].message
    # It asked for manual exposure, in V4L2's 100 us unit, and the gain.
    asked = camera._capture.set_calls
    assert asked[cv2.CAP_PROP_AUTO_EXPOSURE] == 1
    assert asked[cv2.CAP_PROP_EXPOSURE] == 40
    assert asked[cv2.CAP_PROP_GAIN] == 2.0


def test_a_live_webcam_that_stops_is_a_camera_error() -> None:
    camera = WebcamCamera(CameraConfig(source="webcam"), capture_factory=StubCapture)

    with pytest.raises(CameraError, match="stopped delivering"):
        camera.grab()
