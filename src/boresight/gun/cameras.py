"""Where the gun's frames come from: a USB webcam, or a Pi CSI camera.

A USB webcam turns its sensor's data into pictures itself and speaks
plain V4L2 (UVC), so OpenCV opens it on any system. A Pi CSI camera sends
raw sensor data that the Pi's image processor turns into pictures under
libcamera; it never shows up as a plain capture device. The `rpicam-vid`
program that ships with Raspberry Pi OS drives it, and writes raw YUV
frames to a pipe the gun reads. Neither needs a Python binding outside
pip. (`hardware.PiCamera`, through Picamera2, remains for anyone who sets
up a venv that sees the OS's library.)

Every source hands the gun greyscale frames, with exposure, gain and
white balance fixed as far as the camera allows. Automatic exposure
chases the bright panel and loses the markers.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from boresight.gun.config import CameraConfig, ConfigError, rpicam_size_problem

logger = logging.getLogger(__name__)

RPICAM_VID = "rpicam-vid"
STDERR_TAIL_LINES = 20
STOP_TIMEOUT_S = 2.0


class CameraError(RuntimeError):
    """The camera stopped or never started; the message says why."""


def choose_source(
    source: str, which: Callable[[str], str | None] = shutil.which
) -> str:
    """`auto` is the CSI camera where `rpicam-vid` is installed, a webcam
    otherwise; any other source is itself."""
    if source != "auto":
        return source
    return "rpicam" if which(RPICAM_VID) else "webcam"


def open_camera(settings: CameraConfig, which=shutil.which):
    """The configured camera, opened. Raises `ConfigError` for a size the
    chosen source cannot deliver, `CameraError` if it will not open."""
    source = choose_source(settings.source, which)
    logger.info("camera source: %s", source)
    if source == "rpicam":
        if problem := rpicam_size_problem(settings):
            raise ConfigError(problem)
        return RpicamCamera(settings)
    if source == "webcam":
        return WebcamCamera(settings)
    from boresight.gun.hardware import PiCamera

    return PiCamera(settings)


# --- a Pi CSI camera through rpicam-vid ------------------------------------


def rpicam_command(settings: CameraConfig, executable: str = RPICAM_VID) -> list[str]:
    """Raw YUV420 to stdout, forever, with nothing automatic left on."""
    return [
        executable,
        "--timeout", "0",
        "--nopreview",
        "--camera", str(int(settings.device)),
        "--codec", "yuv420",
        "--width", str(settings.width),
        "--height", str(settings.height),
        "--framerate", str(settings.fps),
        # A fixed shutter and gain turn automatic exposure off; fixed
        # white-balance gains turn automatic white balance off.
        "--shutter", f"{settings.exposure_us}us",
        "--gain", str(settings.gain),
        "--awbgains", "1,1",
        "--denoise", "off",
        "--flush",
        "--output", "-",
    ]  # fmt: skip


class RpicamCamera:
    """Frames from a child `rpicam-vid`, read whole off its stdout.

    YUV420 is a full-size Y plane and two quarter-size chroma planes; the
    gun keeps Y. Frames are stamped on arrival (no sensor time comes down
    the pipe), which the capture-time rule handles.
    """

    lossless = False

    def __init__(
        self,
        settings: CameraConfig,
        executable: str = RPICAM_VID,
        popen=subprocess.Popen,
    ) -> None:
        self._width, self._height = settings.width, settings.height
        self._luma = self._width * self._height
        self._frame_bytes = self._luma * 3 // 2
        command = rpicam_command(settings, executable)
        try:
            self._process = popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except OSError as error:
            raise CameraError(
                f"cannot run {executable}: {error}. It comes with Raspberry Pi "
                "OS (the rpicam-apps package); for a USB camera set "
                '[camera] source = "webcam"'
            ) from error
        self._stderr: deque[str] = deque(maxlen=STDERR_TAIL_LINES)
        self._drain = threading.Thread(
            target=self._read_stderr, name="rpicam-stderr", daemon=True
        )
        self._drain.start()
        logger.info(
            "camera: rpicam-vid %dx%d at %d fps, shutter %d us, gain %s, "
            "white balance fixed",
            self._width,
            self._height,
            settings.fps,
            settings.exposure_us,
            settings.gain,
        )

    def _read_stderr(self) -> None:
        for raw in iter(self._process.stderr.readline, b""):
            line = raw.decode(errors="replace").rstrip()
            if line:
                self._stderr.append(line)
                logger.debug("rpicam-vid: %s", line)

    def _failure(self, what: str) -> CameraError:
        try:
            self._process.wait(timeout=STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            pass
        self._drain.join(timeout=1)
        said = "\n".join(self._stderr) or "(nothing on its error output)"
        return CameraError(
            f"rpicam-vid {what} (exit code {self._process.returncode}): {said}"
        )

    def grab(self) -> tuple[np.ndarray, float | None]:
        buffer = bytearray(self._frame_bytes)
        view = memoryview(buffer)
        filled = 0
        stream = self._process.stdout
        while filled < self._frame_bytes:
            count = stream.readinto(view[filled:])
            if not count:
                if filled == 0:
                    raise self._failure("stopped")
                raise self._failure(
                    f"stopped mid-frame, after {filled} of {self._frame_bytes} bytes"
                )
            filled += count
        luma = np.frombuffer(buffer, dtype=np.uint8, count=self._luma)
        return luma.reshape(self._height, self._width), None

    def close(self) -> None:
        process = self._process
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=STOP_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        process.stdout.close()


# --- a USB webcam through OpenCV -------------------------------------------

# V4L2's manual and automatic exposure modes as OpenCV reports them, and
# DirectShow's. A webcam left in either automatic value is not fixed.
_MANUAL_EXPOSURE = 1
_AUTOMATIC_EXPOSURE = {3.0, 0.75}


class WebcamCamera:
    """Any camera OpenCV opens: a USB webcam by index or device path, or
    a video file (which is how the tests drive it).

    Exposure is asked for in V4L2's unit, 100 us. Drivers differ in what
    they honour, so what each property reads back is logged, and a camera
    still on automatic exposure is warned about.
    """

    lossless = False

    def __init__(
        self, settings: CameraConfig, capture_factory=cv2.VideoCapture
    ) -> None:
        device = settings.device
        self._name = str(device)
        self._ends = isinstance(device, str) and Path(device).is_file()
        self._capture = capture_factory(device)
        capture = self._capture
        if not capture.isOpened():
            raise CameraError(
                f"cannot open camera {self._name}: no such device, or it is busy"
            )
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, settings.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.height)
        capture.set(cv2.CAP_PROP_FPS, settings.fps)
        capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, _MANUAL_EXPOSURE)
        capture.set(cv2.CAP_PROP_EXPOSURE, settings.exposure_us / 100)
        capture.set(cv2.CAP_PROP_GAIN, settings.gain)
        capture.set(cv2.CAP_PROP_AUTO_WB, 0)

        def read(prop: int) -> float:
            return float(capture.get(prop))

        logger.info(
            "camera: webcam %s, %dx%d at %.0f fps, exposure %s, gain %s",
            self._name,
            read(cv2.CAP_PROP_FRAME_WIDTH),
            read(cv2.CAP_PROP_FRAME_HEIGHT),
            read(cv2.CAP_PROP_FPS),
            read(cv2.CAP_PROP_EXPOSURE),
            read(cv2.CAP_PROP_GAIN),
        )
        if read(cv2.CAP_PROP_AUTO_EXPOSURE) in _AUTOMATIC_EXPOSURE:
            logger.warning(
                "camera %s kept automatic exposure: it ignores a fixed exposure, "
                "so the markers may wash out against a bright screen",
                self._name,
            )

    def grab(self) -> tuple[np.ndarray, float | None] | None:
        ok, frame = self._capture.read()
        if not ok:
            if self._ends:
                return None  # a video file has run out
            raise CameraError(f"camera {self._name} stopped delivering frames")
        if frame.ndim == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame, None

    def close(self) -> None:
        self._capture.release()
