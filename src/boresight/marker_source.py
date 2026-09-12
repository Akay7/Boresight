"""Choosing between printed and on-screen markers while running.

Owns the one piece of genuinely mutable state in the serving path: which
layout the solver is using, and whether the overlay process is alive.

`AimPipeline` is deliberately stateless and holds fixed collaborators,
so nothing here mutates one. A switch builds a new pipeline and swaps
the reference; the old instance is discarded. The swap is a single
assignment, so a frame gets either the old pipeline or the new one and
never a half-changed one.

The overlay is a child process for a reason beyond convenience. Its
window is input-transparent, takes no keyboard focus and has no title
bar -- so nothing a user can click will remove it, and its own Ctrl-C
handling only helps whoever holds its terminal. When this module
spawned it, that terminal is the server's. An overlay that outlived the
server would be genuinely hard to get rid of, so the parent always
cleans up.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from boresight.inject import CursorBackend
from boresight.layout_source import resolve_layout
from boresight.marker_map import MarkerMap
from boresight.overlay.layout import overlay_layout
from boresight.overlay.qt_backend import GEOMETRY_EVENT
from boresight.pipeline import AimPipeline

# How long to wait for the overlay to report its geometry. Generous:
# starting Qt and opening a display is not instant. Bounded because an
# overlay that neither reports nor exits would otherwise hang the
# request that asked for it.
GEOMETRY_TIMEOUT_S = 20.0

# How long a stopped overlay gets to exit before it is killed.
STOP_TIMEOUT_S = 5.0

logger = logging.getLogger("boresight")


class MarkerSource(Enum):
    PRINTED = "printed"
    SCREEN = "screen"


class MarkerSourceError(RuntimeError):
    """Raised when a marker source could not be selected.

    Carries the overlay's own explanation where there is one -- an
    unsupported compositor, a missing optional dependency, no reachable
    display -- because those are the useful part.
    """


@dataclass(frozen=True)
class OverlayGeometry:
    screen_px: tuple[int, int]
    tag_px: int
    inset_px: int
    # Where on the display the tags were allowed to go, after the
    # desktop's panels took their share. Positions are still expressed
    # against the full screen; this only says where they were placed.
    area_px: tuple[int, int, int, int]

    def as_dict(self) -> dict:
        return {
            "screen_px": list(self.screen_px),
            "area_px": list(self.area_px),
            "tag_px": self.tag_px,
            "inset_px": self.inset_px,
        }


def _overlay_command(display: int | None) -> list[str]:
    """The command used to start the overlay.

    Fixed. Nothing from a request reaches this list -- `display` is an
    int or None, and is rendered by `str()` on an already-parsed
    integer, so there is no path from request content to an argument.
    """
    command = [sys.executable, "-m", "boresight.overlay"]
    if display is not None:
        command += ["--display", str(int(display))]
    return command


def _overlay_environment() -> dict[str, str]:
    """The child's environment, with `boresight` guaranteed importable.

    The parent can import `boresight` by construction -- it is running
    from it. The child is a fresh interpreter, and `-m` resolves against
    its own path, which is not necessarily the same: a server started as
    a script rather than a module, from an unusual working directory, or
    with the package reachable only through PYTHONPATH, can all leave
    the child unable to find what the parent is executing. The symptom
    is a bare "No module named boresight.overlay" from a machine where
    the server itself is obviously working.

    So the directory containing the package the parent actually loaded
    is put at the front of the child's PYTHONPATH. Prepended rather than
    replacing, so an existing PYTHONPATH still applies.
    """
    import boresight

    package_parent = str(Path(boresight.__file__).resolve().parent.parent)
    environment = dict(os.environ)
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{package_parent}{os.pathsep}{existing}" if existing else package_parent
    )
    return environment


class MarkerSourceController:
    """Which markers the solver is using, and the overlay behind them."""

    def __init__(
        self,
        backend: CursorBackend,
        printed_layout: MarkerMap,
        display: int | None = None,
        launcher=subprocess.Popen,
    ) -> None:
        self._backend = backend
        self._printed_layout = printed_layout
        self._display = display
        self._launcher = launcher

        self._source = MarkerSource.PRINTED
        self._layout = printed_layout
        self._pipeline = AimPipeline(printed_layout, backend)
        self._process: subprocess.Popen | None = None
        self._geometry: OverlayGeometry | None = None
        self._last_error: str | None = None

    # --- What the serving path reads ---------------------------------

    @property
    def pipeline(self) -> AimPipeline:
        """The pipeline to solve the next frame with.

        Read per frame rather than captured when a session opens, so a
        switch reaches a phone that is already streaming.
        """
        return self._pipeline

    @property
    def source(self) -> MarkerSource:
        return self._source

    def state(self) -> dict:
        """The current state, with the overlay's liveness checked now.

        Polled on read rather than watched by a supervisor task: the
        state is read whenever the phone asks, which is often enough to
        notice a crash and much simpler than a watchdog.
        """
        if self._source is MarkerSource.SCREEN and not self._overlay_alive():
            self._forget_overlay(
                "the overlay exited on its own; printed markers are active again"
            )

        return {
            "source": self._source.value,
            "overlay_running": self._overlay_alive(),
            "geometry": self._geometry.as_dict() if self._geometry else None,
            "screen_size": list(self._layout.screen_size_mm),
            "error": self._last_error,
        }

    # --- Selecting ----------------------------------------------------

    def select(self, source: MarkerSource) -> dict:
        """Switch to `source`, starting or stopping the overlay.

        Selecting the source that is already active is a no-op, so a
        double tap on the phone does not restart the overlay.
        """
        if source is self._source and (
            source is MarkerSource.PRINTED or self._overlay_alive()
        ):
            return self.state()

        if source is MarkerSource.PRINTED:
            if self._process is not None:
                logger.info("printed markers: stopping the overlay")
            self.stop_overlay()
            self._use(self._printed_layout, MarkerSource.PRINTED)
            self._last_error = None
            return self.state()

        return self._start_screen_markers()

    def _start_screen_markers(self) -> dict:
        self.stop_overlay()  # never two overlays at once
        try:
            geometry = self._launch_and_read_geometry()
        except MarkerSourceError as error:
            # Printed markers stay active. Reporting the requested
            # source as active while nothing is on screen would leave
            # the solver using a layout for tags that do not exist,
            # which presents as terrible aim with no visible cause.
            logger.warning("on-screen markers unavailable: %s", error)
            self._last_error = str(error)
            self.stop_overlay()
            raise

        # Built from exactly the numbers the overlay reported, so the
        # drawn and solved layouts are the same layout.
        reserved = (geometry.screen_px[1] - geometry.area_px[3]) + (
            geometry.screen_px[0] - geometry.area_px[2]
        )
        logger.info(
            "on-screen markers: overlay running on %dx%d, tags %dpx inset %dpx%s",
            geometry.screen_px[0],
            geometry.screen_px[1],
            geometry.tag_px,
            geometry.inset_px,
            f", {reserved}px reserved by desktop panels" if reserved else "",
        )
        self._geometry = geometry
        self._use(
            overlay_layout(
                geometry.screen_px,
                geometry.tag_px,
                geometry.inset_px,
                area_px=geometry.area_px,
            ),
            MarkerSource.SCREEN,
        )
        self._last_error = None
        return self.state()

    def _use(self, layout: MarkerMap, source: MarkerSource) -> None:
        # A new pipeline, not a mutated one: AimPipeline promises it
        # holds no mutable state and this keeps that true.
        self._layout = layout
        self._pipeline = AimPipeline(layout, self._backend)
        self._source = source

    # --- The child process --------------------------------------------

    def _launch_and_read_geometry(self) -> OverlayGeometry:
        try:
            process = self._launcher(
                _overlay_command(self._display),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=_overlay_environment(),
            )
        except OSError as error:
            raise MarkerSourceError(f"could not start the overlay: {error}") from error

        self._process = process
        return self._read_geometry(process)

    def _read_geometry(self, process) -> OverlayGeometry:
        try:
            line = _readline_with_timeout(process, GEOMETRY_TIMEOUT_S)
        except TimeoutError:
            raise MarkerSourceError(
                "the overlay did not report its geometry within "
                f"{GEOMETRY_TIMEOUT_S:g}s and was stopped"
            ) from None

        if not line:
            # Exited without reporting. Its own message is the useful
            # part: an unsupported compositor, a missing extra, no
            # display.
            raise MarkerSourceError(_explain_exit(process))

        try:
            message = json.loads(line)
        except ValueError:
            raise MarkerSourceError(
                f"the overlay reported something unreadable: {line.strip()!r}"
            ) from None

        if message.get("event") != GEOMETRY_EVENT:
            raise MarkerSourceError(f"unexpected message from the overlay: {message!r}")

        screen = message["screen_px"]
        screen_px = (int(screen[0]), int(screen[1]))
        area = message.get("area_px") or [0, 0, *screen_px]
        return OverlayGeometry(
            screen_px=screen_px,
            tag_px=int(message["tag_px"]),
            inset_px=int(message["inset_px"]),
            area_px=tuple(int(value) for value in area),
        )

    def _overlay_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _forget_overlay(self, reason: str | None) -> None:
        self._process = None
        self._geometry = None
        self._use(self._printed_layout, MarkerSource.PRINTED)
        if reason:
            self._last_error = reason

    def stop_overlay(self) -> None:
        """Terminate the overlay if one is running.

        Safe to call when none is. Called on shutdown, on switching to
        printed markers, and before starting a replacement.
        """
        process = self._process
        self._process = None
        self._geometry = None
        if process is None or process.poll() is not None:
            return

        process.terminate()
        try:
            process.wait(timeout=STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=STOP_TIMEOUT_S)

    def shutdown(self) -> None:
        self.stop_overlay()


def _readline_with_timeout(process, timeout: float) -> str:
    """One line from the child's stdout, or TimeoutError.

    A thread rather than `select`, so this works the same on Windows,
    where a pipe is not selectable.
    """
    import threading

    result: list[str] = []

    def read() -> None:
        line = process.stdout.readline()
        result.append(line)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    reader.join(timeout)
    if reader.is_alive():
        process.kill()
        raise TimeoutError
    return result[0] if result else ""


def _explain_exit(process) -> str:
    """Why the overlay stopped, in its own words where it left any."""
    try:
        stderr = process.stderr.read() or ""
    except ValueError, OSError:  # pragma: no cover - closed pipe
        stderr = ""
    process.wait(timeout=STOP_TIMEOUT_S)
    detail = stderr.strip()
    if detail:
        return detail
    return f"the overlay exited with status {process.returncode} without explanation"


def printed_controller(
    backend: CursorBackend, spec: str = "file", display: int | None = None, **kwargs
) -> MarkerSourceController:
    """A controller starting on the printed layout named by `spec`."""
    return MarkerSourceController(backend, resolve_layout(spec), display, **kwargs)
