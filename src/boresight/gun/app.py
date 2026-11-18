"""The gun's run loop: capture, aim, trigger, and the numbers to show for it.

Three threads. Capture hands the newest frame to a one-frame slot and never
waits for the aim; the aim thread takes whatever is newest, so a slow solve
drops frames instead of queueing them. The trigger thread polls the button
and speaks to the host directly, never behind a frame.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Protocol

import numpy as np

from boresight.aim_hold import HoldingPipeline
from boresight.gun.config import Loaded
from boresight.gun.hid import HidGadgetBackend
from boresight.gun.led import State, StatusIndicator
from boresight.gun.pins import Debouncer
from boresight.gun.timing import capture_time
from boresight.inject import SmoothingCursorBackend
from boresight.one_euro import OneEuroFilter
from boresight.pipeline import AimPipeline, FrameOutcome

logger = logging.getLogger(__name__)

POLL_S = 0.002
REPORT_EVERY_S = 5.0


class Camera(Protocol):
    # A lossless camera (recorded frames) waits for each frame to be taken
    # instead of overwriting it, so a test sees every frame.
    lossless: bool

    def grab(self) -> tuple[np.ndarray, float | None] | None:
        """The next frame and the sensor's capture time in seconds on the
        monotonic clock (None if unknown). None when there will be no more."""

    def close(self) -> None: ...


class TriggerInput(Protocol):
    def read(self) -> bool:
        """Whether the button is physically down right now."""


class FrameSlot:
    """Holds at most one frame: the newest."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._item: tuple[np.ndarray, float] | None = None
        self._closed = False
        self.dropped = 0

    def put(self, frame: np.ndarray, t: float, *, wait: bool = False) -> None:
        with self._cond:
            if wait:
                self._cond.wait_for(lambda: self._item is None or self._closed)
            elif self._item is not None:
                self.dropped += 1
            self._item = (frame, t)
            self._cond.notify_all()

    def take(self, timeout: float) -> tuple[np.ndarray, float] | None:
        with self._cond:
            self._cond.wait_for(lambda: self._item is not None or self._closed, timeout)
            item, self._item = self._item, None
            self._cond.notify_all()
            return item

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    @property
    def finished(self) -> bool:
        with self._cond:
            return self._closed and self._item is None


class Gun:
    def __init__(
        self,
        loaded: Loaded,
        camera: Camera,
        backend: HidGadgetBackend,
        trigger: TriggerInput,
        indicator: StatusIndicator,
        clock: Callable[[], float] = time.monotonic,
        pipeline=None,
    ) -> None:
        """`pipeline` is a server session's (`marker_source.SessionPipeline`):
        its own smoothing, hold and current layout, as the local output
        uses. Without one, the gun builds its own over `backend` from the
        configured layout, as the USB output does."""
        self._loaded = loaded
        self._camera = camera
        self._backend = backend
        self._trigger = trigger
        self._indicator = indicator
        self._clock = clock
        self._slot = FrameSlot()
        self.frames = 0
        self.solved = 0
        self.camera_failed: BaseException | None = None

        if pipeline is not None:
            pipeline.zero = loaded.zero
            self._aim = lambda frame, t: pipeline.process_frame(
                frame, t=t, lens=loaded.lens
            )
            return
        tuning = loaded.config.tuning
        cursor = (
            SmoothingCursorBackend(
                backend, OneEuroFilter(min_cutoff=tuning.min_cutoff, beta=tuning.beta)
            )
            if tuning.smoothing
            else backend
        )
        solver = AimPipeline(loaded.marker_map, cursor)
        holding = HoldingPipeline(solver, cursor, hold_s=tuning.hold_s)
        detector = solver.session_detector()
        self._aim = lambda frame, t: holding.process_frame(
            frame, t=t, detector=detector, lens=loaded.lens, zero=loaded.zero
        )

    def process(self, frame: np.ndarray, t: float) -> bool:
        """One frame through the pipeline. Whether it solved."""
        result = self._aim(frame, t)
        solved = result.outcome is FrameOutcome.SOLVED
        self.frames += 1
        self.solved += solved
        self._indicator.set_state(State.AIMING if solved else State.SEARCHING)
        return solved

    def run(self, stop: threading.Event) -> int:
        """Aims until `stop` is set or the camera ends. 0 on a clean end,
        1 if the camera failed."""
        threads = [
            threading.Thread(target=self._capture, args=(stop,), name="capture"),
            threading.Thread(target=self._watch_trigger, args=(stop,), name="trigger"),
        ]
        self._indicator.set_state(State.SEARCHING)
        for thread in threads:
            thread.start()
        started = last_report = self._clock()
        last_counts = (0, 0, 0)
        try:
            while not stop.is_set() and not self._slot.finished:
                item = self._slot.take(timeout=0.1)
                if item is not None:
                    self.process(*item)
                now = self._clock()
                if now - last_report >= REPORT_EVERY_S:
                    last_counts = self._report(now - last_report, last_counts)
                    last_report = now
        finally:
            stop.set()
            self._slot.close()
            for thread in threads:
                thread.join(timeout=2)
            try:
                self._camera.close()
            finally:
                # Never leave the host with a button held.
                self._backend.close()
        if self.camera_failed is not None:
            self._indicator.set_state(State.ERROR)
            return 1
        logger.info(
            "ran %.0f s, %d frames, %d solved",
            self._clock() - started,
            self.frames,
            self.solved,
        )
        return 0

    def _report(
        self, seconds: float, last: tuple[int, int, int]
    ) -> tuple[int, int, int]:
        counts = (self.frames, self.solved, self._slot.dropped)
        frames, solved, dropped = (a - b for a, b in zip(counts, last, strict=True))
        logger.info(
            "%.1f fps, %d%% solved, %d dropped",
            frames / seconds,
            round(100 * solved / frames) if frames else 0,
            dropped,
        )
        return counts

    def _capture(self, stop: threading.Event) -> None:
        try:
            while not stop.is_set():
                grabbed = self._camera.grab()
                if grabbed is None:
                    break
                frame, sensor_s = grabbed
                t = capture_time(sensor_s, time.monotonic())
                self._slot.put(frame, t, wait=self._camera.lossless)
        except Exception as error:  # a camera that dies must not hold the button
            logger.exception("camera failed")
            self.camera_failed = error
            stop.set()
        finally:
            self._slot.close()

    def _watch_trigger(self, stop: threading.Event) -> None:
        debounce = Debouncer(self._loaded.config.pins.debounce_ms)
        while not stop.is_set():
            changed = debounce.update(self._trigger.read(), self._clock() * 1000)
            if changed is True:
                self._backend.press()
            elif changed is False:
                self._backend.release()
            stop.wait(POLL_S)
