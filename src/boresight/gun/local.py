"""The local output: the gun aiming at the display its own computer drives.

The parts are the server's own:
- the marker-source controller starts the on-screen overlay and solves
  against exactly the layout it reports
- the cursor is the uinput absolute pointer, which any program on the
  display, an emulator included, reads as the mouse
- the aim goes through the controller's per-session pipeline, with its
  smoothing, hold and edge margin

The gun's own loop supplies the camera frames and the GPIO trigger. If
the overlay dies, the tags are gone, so the gun stops rather than aim
against a layout that is no longer on screen.
"""

from __future__ import annotations

import logging
import threading

from boresight.gun.app import Camera, Gun, TriggerInput
from boresight.gun.config import Loaded
from boresight.gun.led import State, StatusIndicator
from boresight.marker_source import (
    MarkerSource,
    MarkerSourceController,
    MarkerSourceError,
)
from boresight.settings import Tuning

logger = logging.getLogger("boresight.gun.local")

WATCH_EVERY_S = 0.5


class LocalCursor:
    """The cursor as the gun's loop wants it: closing releases a held
    button first, then closes the device if it has anything to close."""

    def __init__(self, cursor) -> None:
        self._cursor = cursor

    def move_absolute(self, x: float, y: float) -> None:
        self._cursor.move_absolute(x, y)

    def press(self) -> None:
        self._cursor.press()

    def release(self) -> None:
        self._cursor.release()

    def click(self) -> None:
        self._cursor.click()

    def idle(self) -> None:
        self._cursor.idle()

    def close(self) -> None:
        try:
            self._cursor.release()
        finally:
            close = getattr(self._cursor, "close", None)
            if close is not None:
                close()


def controller_for(loaded: Loaded, cursor, launcher=None) -> MarkerSourceController:
    """The server's marker-source controller, with the gun's overlay
    settings and tuning. Printed markers are its starting point and its
    fallback; the local output switches it to on-screen at once."""
    from boresight.marker_map import MarkerMap

    overlay = loaded.config.overlay
    tuning = loaded.config.tuning
    if not tuning.smoothing:
        logger.info("the local output always smooths, as the server does")
    fixed = Tuning(min_cutoff=tuning.min_cutoff, beta=tuning.beta, hold_s=tuning.hold_s)
    extra = {} if launcher is None else {"launcher": launcher}
    return MarkerSourceController(
        cursor,
        # Never solved against: on-screen markers are selected before the
        # first frame, and a failure to start them stops the gun.
        MarkerMap(screen_size_mm=(1.0, 1.0), markers={}),
        display=overlay.display,
        overlay_extra_margin_px=overlay.extra_margin_px,
        overlay_picture_aspect=overlay.picture_aspect,
        tuning=lambda: fixed,
        **extra,
    )


def run_local(
    loaded: Loaded,
    camera: Camera,
    cursor,
    trigger: TriggerInput,
    indicator: StatusIndicator,
    stop: threading.Event,
    launcher=None,
    watch_every_s: float = WATCH_EVERY_S,
) -> int:
    """Aim until `stop`. 0 on a clean end; 1 if the overlay would not start
    or died, or the camera failed."""
    local_cursor = LocalCursor(cursor)
    controller = controller_for(loaded, cursor, launcher)
    try:
        try:
            controller.select(MarkerSource.SCREEN)
        except MarkerSourceError as error:
            logger.error("the on-screen markers did not start: %s", error)
            indicator.set_state(State.ERROR)
            camera.close()
            local_cursor.close()
            return 1
        geometry = controller.state()["geometry"] or {}
        logger.info("on-screen markers up: %s", geometry)

        gun = Gun(
            loaded,
            camera,
            local_cursor,
            trigger,
            indicator,
            pipeline=controller.session_pipeline(cursor),
        )
        overlay_died = threading.Event()

        def watch() -> None:
            while not stop.wait(watch_every_s):
                state = controller.state()
                if state["source"] != MarkerSource.SCREEN.value:
                    logger.error(
                        "the on-screen markers are gone, stopping: %s", state["error"]
                    )
                    overlay_died.set()
                    stop.set()

        watcher = threading.Thread(target=watch, name="overlay-watch", daemon=True)
        watcher.start()
        code = gun.run(stop)
        stop.set()
        watcher.join(timeout=2)
        if overlay_died.is_set():
            indicator.set_state(State.ERROR)
            return 1
        return code
    finally:
        controller.shutdown()
