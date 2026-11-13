"""The Pi itself: a CSI camera through picamera2 and GPIO through gpiozero.

Imported lazily, only on a Pi. These are thin on purpose; everything with a
rule in it lives in modules that run anywhere. Checked by hand on a Zero 2 W
(see deploy/pi/README.md), not by the test suite.
"""

from __future__ import annotations

import logging
import time

import numpy as np

from boresight.gun.config import CameraConfig

logger = logging.getLogger(__name__)


class PiCamera:
    """Greyscale frames from the CSI camera, with exposure and gain fixed.

    Asks libcamera for YUV420 and keeps the Y plane: the detector wants
    luma, so no JPEG is encoded or decoded between sensor and solver.
    """

    lossless = False

    def __init__(self, settings: CameraConfig) -> None:
        from picamera2 import Picamera2

        self._settings = settings
        self._camera = Picamera2()
        configuration = self._camera.create_video_configuration(
            main={"size": (settings.width, settings.height), "format": "YUV420"},
            controls={
                "AeEnable": False,
                "AwbEnable": False,
                "ExposureTime": settings.exposure_us,
                "AnalogueGain": settings.gain,
                "FrameRate": float(settings.fps),
            },
        )
        self._camera.configure(configuration)
        self._camera.start()
        applied = self._camera.capture_metadata()
        logger.info(
            "camera: %dx%d, exposure %s us, gain %s, auto exposure off",
            settings.width,
            settings.height,
            applied.get("ExposureTime"),
            applied.get("AnalogueGain"),
        )

    def grab(self) -> tuple[np.ndarray, float | None]:
        request = self._camera.capture_request()
        try:
            yuv = request.make_array("main")
            sensor_ns = request.get_metadata().get("SensorTimestamp")
        finally:
            request.release()
        luma = yuv[: self._settings.height, : self._settings.width]
        # SensorTimestamp is CLOCK_BOOTTIME; the aim filter's clock is the
        # monotonic one. They differ by time spent suspended, which on a
        # gun is none, and `capture_time` rejects an implausible value.
        sensor_s = None if sensor_ns is None else sensor_ns / 1e9
        return luma.copy(), _boottime_to_monotonic(sensor_s)

    def close(self) -> None:
        self._camera.stop()
        self._camera.close()


def _boottime_to_monotonic(boottime_s: float | None) -> float | None:
    if boottime_s is None:
        return None
    return boottime_s - time.clock_gettime(time.CLOCK_BOOTTIME) + time.monotonic()


class GpioTrigger:
    """A button between the pin and ground, on the internal pull-up."""

    def __init__(self, pin: int) -> None:
        from gpiozero import DigitalInputDevice

        self._device = DigitalInputDevice(pin, pull_up=True, bounce_time=None)

    def read(self) -> bool:
        return not self._device.value  # pulled up: low is pressed

    def close(self) -> None:
        self._device.close()


class GpioLed:
    def __init__(self, pin: int) -> None:
        from gpiozero import DigitalOutputDevice

        self._device = DigitalOutputDevice(pin)

    def set(self, on: bool) -> None:
        self._device.value = 1 if on else 0

    def close(self) -> None:
        self._device.close()
