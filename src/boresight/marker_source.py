"""Choosing between printed and on-screen markers while running.

Owns the one piece of genuinely mutable state in the serving path: which
layout the solver is using, and whether the overlay process is alive.

`AimPipeline` is deliberately stateless and holds fixed collaborators,
so nothing here mutates one. A switch builds a new pipeline and swaps
the reference; the old instance is discarded. The swap is a single
assignment, so a frame gets either the old pipeline or the new one and
never a half-changed one.

Smoothing and the dropout hold are per session, not per controller:
several cameras can stream at once, and one filter fed by all of them
blends their aim into a point none of them is aiming at. Each session
asks `session_pipeline()` for a `SessionPipeline` of its own: a
`SmoothingCursorBackend` whose filter lives as long as the session, so
a marker-source switch does not discontinue smoothing, and a
`HoldingPipeline` (`aim_hold.py`) over whichever `AimPipeline` is
current, rebuilt when a switch replaces it, so a held position never
crosses from one source into another. The controller itself holds only
the stateless solver.

The overlay is a child process for a reason beyond convenience. Its
window is input-transparent, takes no keyboard focus and has no title
bar -- so nothing a user can click will remove it, and its own Ctrl-C
handling only helps whoever holds its terminal. When this module
spawned it, that terminal is the server's. An overlay that outlived the
server would be genuinely hard to get rid of, so the parent always
cleans up.

Everything the overlay writes is read as it is written, on both pipes,
for as long as it runs: a pipe holds about 64 KiB, and a child whose
pipe nobody reads blocks on its next write while still looking alive.
See `_PipeDrain`.

Every change of marker source -- selecting one, changing the overlay
margin, shutting down -- happens under one lock. The routes that call
this are plain `def`s run in FastAPI's threadpool, so two taps on the
phone are two threads here at once, and without the lock both could
start an overlay. Reading the state and reading the pipeline never
wait on it.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np

from boresight.aim_hold import HoldingPipeline
from boresight.detect import Detector
from boresight.inject import CursorBackend, SmoothingCursorBackend
from boresight.layout_source import resolve_layout
from boresight.lens import LensModel
from boresight.marker_map import MarkerMap
from boresight.one_euro import OneEuroFilter
from boresight.overlay.layout import overlay_layout
from boresight.overlay.qt_backend import GEOMETRY_EVENT
from boresight.pipeline import AimPipeline, FrameResult
from boresight.settings import Tuning

# How long to wait for the overlay to report its geometry. Generous:
# starting Qt and opening a display is not instant. Bounded because an
# overlay that neither reports nor exits would otherwise hang the
# request that asked for it.
GEOMETRY_TIMEOUT_S = 20.0

# How long a stopped overlay gets to exit before it is killed.
STOP_TIMEOUT_S = 5.0

# How much of the overlay's output is kept for an error message. The
# rest is still read -- it has to be, or the child blocks -- and goes
# to the log. Lines longer than the cap are kept in pieces, so the
# memory held is bounded whatever the child writes.
OUTPUT_TAIL_LINES = 20
OUTPUT_LINE_CHARS = 1000

logger = logging.getLogger("boresight")
# The child's own words, line by line, at DEBUG: a chatty overlay is
# exactly the case the draining exists for, and at INFO it would bury
# the server's log. Failures surface its last words at WARNING anyway.
overlay_logger = logging.getLogger("boresight.overlay")


def _aim_filter(tuning: Tuning) -> OneEuroFilter:
    """A new session's filter, built from the tuning in effect.

    Both knobs are tuned by feel, not measurement (see one_euro.py's
    module docstring), which is why they are live settings
    (`settings.py`) rather than constants: a session built here keeps
    following them through `SessionPipeline`.
    """
    return OneEuroFilter(min_cutoff=tuning.min_cutoff, beta=tuning.beta)


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


def _overlay_command(display: int | None, extra_margin_px: int = 0) -> list[str]:
    """The command used to start the overlay.

    Fixed. Nothing from a request reaches this list -- both `display`
    and `extra_margin_px` are set at server startup, not per request,
    and each is rendered by `str()` on an already-parsed number, so
    there is no path from request content to an argument.
    """
    command = [sys.executable, "-m", "boresight.overlay"]
    if display is not None:
        command += ["--display", str(int(display))]
    if extra_margin_px:
        command += ["--extra-margin-px", str(int(extra_margin_px))]
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


class SessionPipeline:
    """One session's aim: its own smoothing, dropout hold and detector.

    The filter is this object's for its whole life, so a marker-source
    switch does not discontinue smoothing. The `HoldingPipeline` is
    rebuilt whenever the controller's current `AimPipeline` is replaced,
    so a position held from the old source never reaches the new one.
    Only this session's frames feed either.

    Tuning is read once per frame, as one immutable snapshot, and
    applied here -- on the thread processing this session's frame, the
    only one that ever touches its filter and hold -- so a live change
    needs no lock on the frame path and reaches a session already
    streaming on its next frame, without resetting its smoothing.
    """

    def __init__(self, controller: MarkerSourceController, cursor: CursorBackend):
        self._controller = controller
        self._tuning = controller.tuning()
        self._filter = _aim_filter(self._tuning)
        self._backend = SmoothingCursorBackend(cursor, filter=self._filter)
        self._solver: AimPipeline | None = None
        self._holding: HoldingPipeline | None = None
        self._detector: Detector | None = None

    def process_frame(
        self,
        frame: np.ndarray,
        *,
        debug: bool = False,
        t: float | None = None,
        lens: LensModel | None = None,
    ) -> FrameResult:
        tuning = self._controller.tuning()
        if tuning is not self._tuning:
            self._tuning = tuning
            self._filter.tune(tuning.min_cutoff, tuning.beta)
            if self._holding is not None:
                self._holding.hold_s = tuning.hold_s
        solver = self._controller.pipeline
        if solver is not self._solver or self._holding is None:
            self._solver = solver
            self._holding = HoldingPipeline(solver, self._backend, hold_s=tuning.hold_s)
            # Renewed with the hold: the markers it was tracking belong
            # to the source being left.
            self._detector = solver.session_detector()
        return self._holding.process_frame(
            frame, debug=debug, t=t, detector=self._detector, lens=lens
        )


class MarkerSourceController:
    """Which markers the solver is using, and the overlay behind them."""

    def __init__(
        self,
        backend: CursorBackend,
        printed_layout: MarkerMap,
        display: int | None = None,
        launcher=subprocess.Popen,
        overlay_extra_margin_px: int = 0,
        tracked_detection: bool = True,
        tuning: Callable[[], Tuning] | None = None,
    ) -> None:
        # Unwrapped: smoothing belongs to each session (see
        # `session_pipeline`). This is only the pipeline's default
        # emitter, which a session always overrides per frame.
        self._backend = backend
        self._printed_layout = printed_layout
        self._display = display
        self._launcher = launcher
        self._overlay_extra_margin_px = overlay_extra_margin_px
        # Whether sessions detect through a `MarkerTracker` (see
        # `AimPipeline.session_detector`) or search every frame in full.
        self._tracked_detection = tracked_detection
        # The tuning in effect, read by every session per frame. A
        # callable, so the live store can swap its snapshot underneath
        # (`settings.LiveSettings`); without one, the defaults, as one
        # object so a session never sees it as a change.
        defaults = Tuning()
        self.tuning = tuning if tuning is not None else lambda: defaults

        self._source = MarkerSource.PRINTED
        self._layout = printed_layout
        self._pipeline = AimPipeline(
            printed_layout, self._backend, tracking=tracked_detection
        )
        self._process: subprocess.Popen | None = None
        self._stdout: _PipeDrain | None = None
        self._stderr: _PipeDrain | None = None
        self._geometry: OverlayGeometry | None = None
        self._last_error: str | None = None

        # Held for the whole of any change of source, including the
        # wait for an overlay to report its geometry. A `threading`
        # lock, not an `asyncio` one: the callers are threadpool
        # threads and, for shutdown, the event loop thread. Not
        # reentrant on purpose -- the `_locked` helpers assume it is
        # held and never take it again.
        self._lock = threading.Lock()
        self._switching = False
        self._closed = False

    # --- What the serving path reads ---------------------------------

    @property
    def pipeline(self) -> AimPipeline:
        """The stateless solver for the current marker source.

        Read per frame rather than captured when a session opens, so a
        switch reaches a phone that is already streaming. Sessions solve
        through their own `SessionPipeline`, which reads this.
        """
        return self._pipeline

    def session_pipeline(self, cursor: CursorBackend) -> SessionPipeline:
        """A new session's own smoothing and hold, emitting to `cursor`."""
        return SessionPipeline(self, cursor)

    @property
    def source(self) -> MarkerSource:
        return self._source

    @property
    def overlay_extra_margin_px(self) -> int:
        return self._overlay_extra_margin_px

    def state(self) -> dict:
        """The current state, with the overlay's liveness checked now.

        Polled on read rather than watched by a supervisor task: the
        state is read whenever the phone asks, which is often enough to
        notice a crash and much simpler than a watchdog.

        Never waits for a switch in progress, which can take as long as
        an overlay start. During one it reports `switching` and skips
        the liveness check: mid-restart the old overlay has already
        been stopped on purpose, and must not be reported as having
        died. The snapshot can then mix old and new values; the
        switch's own response is the authoritative result.
        """
        if not self._lock.acquire(blocking=False):
            return self._snapshot()
        try:
            self._reap_locked()
            return self._snapshot()
        finally:
            self._lock.release()

    def _reap_locked(self) -> None:
        if self._source is MarkerSource.SCREEN and not self._overlay_alive():
            reason = "the overlay exited on its own; printed markers are active again"
            last = self._stderr.last_line() if self._stderr else ""
            if last:
                reason = f"{reason} (its last words: {last})"
            logger.warning("%s", reason)
            self._forget_overlay(reason)

    def _snapshot(self) -> dict:
        return {
            "source": self._source.value,
            "overlay_running": self._overlay_alive(),
            "geometry": self._geometry.as_dict() if self._geometry else None,
            "screen_size": list(self._layout.screen_size_mm),
            "error": self._last_error,
            "overlay_extra_margin_px": self._overlay_extra_margin_px,
            "switching": self._switching,
        }

    # --- Selecting ----------------------------------------------------

    def set_overlay_extra_margin_px(self, value: int) -> dict:
        """Set the overlay's manual panel-avoidance margin.

        If on-screen markers are active, the overlay is restarted with
        the new value immediately -- through `_start_screen_markers()`,
        the same path `select()` uses, so a failure to restart (an
        overlay that no longer starts, say) is reported the same way:
        raised as `MarkerSourceError`, printed markers left active. If
        printed markers are active, only the stored value changes; it
        takes effect the next time on-screen markers are selected.

        Setting the value already in effect is a no-op, like selecting
        the active source: a restart would produce the same overlay.
        """
        with self._switching_locked():
            self._reap_locked()
            unchanged = value == self._overlay_extra_margin_px
            self._overlay_extra_margin_px = value
            if self._source is MarkerSource.SCREEN and not unchanged:
                return self._start_screen_markers_locked()
            return self._snapshot()

    def select(self, source: MarkerSource) -> dict:
        """Switch to `source`, starting or stopping the overlay.

        Selecting the source that is already active is a no-op, so a
        double tap on the phone does not restart the overlay. The check
        is made under the lock, so the second of two concurrent taps
        sees what the first one did rather than repeating it.
        """
        with self._switching_locked():
            # A dead overlay is forgotten first, so "already on screen"
            # below means an overlay that is actually running.
            self._reap_locked()
            if source is self._source:
                return self._snapshot()

            if source is MarkerSource.PRINTED:
                if self._process is not None:
                    logger.info("printed markers: stopping the overlay")
                self._stop_overlay_locked()
                self._use(self._printed_layout, MarkerSource.PRINTED)
                self._last_error = None
                return self._snapshot()

            return self._start_screen_markers_locked()

    @contextmanager
    def _switching_locked(self):
        """Hold the lock, reporting a switch in progress meanwhile."""
        with self._lock:
            self._switching = True
            try:
                yield
            finally:
                self._switching = False

    def _start_screen_markers_locked(self) -> dict:
        self._stop_overlay_locked()  # never two overlays at once
        try:
            if self._closed:
                raise MarkerSourceError("the server is shutting down")
            geometry = self._launch_and_read_geometry()
        except MarkerSourceError as error:
            # Printed markers stay active. Reporting the requested
            # source as active while nothing is on screen would leave
            # the solver using a layout for tags that do not exist,
            # which presents as terrible aim with no visible cause.
            logger.warning("on-screen markers unavailable: %s", error)
            self._last_error = str(error)
            self._stop_overlay_locked()
            # Already printed on a first selection; not on a margin
            # restart, whose old overlay has just been stopped.
            self._use(self._printed_layout, MarkerSource.PRINTED)
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
        return self._snapshot()

    def _use(self, layout: MarkerMap, source: MarkerSource) -> None:
        # A new pipeline, not a mutated one: AimPipeline promises it
        # holds no mutable state and this keeps that true. Each
        # session's `SessionPipeline` notices the new object and drops
        # its held position, which belongs to the source being left.
        self._layout = layout
        self._pipeline = AimPipeline(
            layout, self._backend, tracking=self._tracked_detection
        )
        self._source = source

    # --- The child process --------------------------------------------

    def _launch_and_read_geometry(self) -> OverlayGeometry:
        try:
            process = self._launcher(
                _overlay_command(self._display, self._overlay_extra_margin_px),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=_overlay_environment(),
            )
        except OSError as error:
            raise MarkerSourceError(f"could not start the overlay: {error}") from error

        # Both pipes are read from here on, for the life of the child;
        # see `_PipeDrain`. Started before anything waits on the
        # geometry, since an overlay can fill stderr before it reports.
        self._stdout = _PipeDrain(process.stdout, "stdout")
        self._stderr = _PipeDrain(process.stderr, "stderr")
        # Stored before `_closed` is checked, while `shutdown()` sets
        # `_closed` before reading this: whichever runs second sees the
        # other, so a start can never slip past a shutdown unnoticed.
        self._process = process
        if self._closed:
            raise MarkerSourceError("the server is shutting down")
        try:
            geometry = self._read_geometry(process, self._stdout, self._stderr)
        except MarkerSourceError:
            if self._closed:
                # Shutdown stopped it mid-start; that is the real reason.
                raise MarkerSourceError("the server is shutting down") from None
            raise
        if self._closed:
            raise MarkerSourceError("the server is shutting down")
        return geometry

    def _read_geometry(
        self, process, stdout: _PipeDrain, stderr: _PipeDrain
    ) -> OverlayGeometry:
        try:
            line = stdout.first_line(GEOMETRY_TIMEOUT_S)
        except TimeoutError:
            process.kill()
            raise MarkerSourceError(
                "the overlay did not report its geometry within "
                f"{GEOMETRY_TIMEOUT_S:g}s and was stopped"
            ) from None

        if not line:
            # Exited without reporting. Its own message is the useful
            # part: an unsupported compositor, a missing extra, no
            # display.
            raise MarkerSourceError(_explain_exit(process, stderr))

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
        """Terminate the overlay if one is running, and use printed markers.

        Safe to call when none is.
        """
        with self._switching_locked():
            self._stop_overlay_locked()
            self._use(self._printed_layout, MarkerSource.PRINTED)

    def _stop_overlay_locked(self) -> None:
        """Called on shutdown, on switching to printed markers, and
        before starting a replacement. Leaves the source to the caller.
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
        """Stop the overlay for good, including one still starting.

        A start waiting for the overlay's geometry holds the lock for
        up to `GEOMETRY_TIMEOUT_S`. Rather than wait that out, its
        process is terminated, which ends the wait at once (the child's
        stdout closes) and fails the start through its ordinary path.
        `_closed` is set first, so nothing starts an overlay after this.
        """
        self._closed = True
        if not self._lock.acquire(blocking=False):
            starting = self._process
            if starting is not None and starting.poll() is None:
                logger.info("shutting down: stopping an overlay that was starting")
                starting.terminate()
            self._lock.acquire()
        try:
            self._stop_overlay_locked()
            self._use(self._printed_layout, MarkerSource.PRINTED)
        finally:
            self._lock.release()


class _PipeDrain:
    """Reads one of the child's pipes, continuously, until it closes.

    The reason this exists: nothing else reads these pipes while the
    overlay runs, and a pipe nobody reads fills (about 64 KiB) and then
    blocks the child on its next write -- an overlay that is still
    "alive" but frozen, or stuck before it ever reports its geometry.

    A thread rather than `select`, so this works the same on Windows,
    where a pipe is not selectable. A daemon, so a pipe held open by
    some grandchild never keeps the server from exiting.

    The first line is handed to whoever waits in `first_line()` -- on
    stdout, that is the geometry report -- so one reader owns the pipe
    from start to end, with no hand-over in which it goes unread.
    Every line goes to the log at DEBUG; the last `OUTPUT_TAIL_LINES`
    are kept for an error message, each at most `OUTPUT_LINE_CHARS`.
    """

    def __init__(self, stream, name: str) -> None:
        self._name = name
        self._tail: deque[str] = deque(maxlen=OUTPUT_TAIL_LINES)
        self._first: queue.Queue[str] = queue.Queue(maxsize=1)
        self._thread = threading.Thread(
            target=self._run, args=(stream,), name=f"overlay-{name}", daemon=True
        )
        self._thread.start()

    def _run(self, stream) -> None:
        delivered = False
        try:
            while stream is not None:
                try:
                    line = stream.readline(OUTPUT_LINE_CHARS)
                except (ValueError, OSError):  # pragma: no cover - closed pipe
                    break
                if not line:
                    break
                if not delivered:
                    self._first.put(line)
                    delivered = True
                text = line.rstrip("\r\n")
                if text:
                    self._tail.append(text)
                    overlay_logger.debug("overlay %s: %s", self._name, text)
        finally:
            if not delivered:
                self._first.put("")  # EOF before any line

    def first_line(self, timeout: float) -> str:
        """The first line written, "" at EOF, or TimeoutError."""
        try:
            return self._first.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError from None

    def join(self, timeout: float) -> None:
        self._thread.join(timeout)

    def tail(self) -> str:
        return "\n".join(self._tail)

    def last_line(self) -> str:
        return self._tail[-1] if self._tail else ""


def _explain_exit(process, stderr: _PipeDrain) -> str:
    """Why the overlay stopped, in its own words where it left any.

    Taken from what the stderr drain kept, once it has reached EOF.
    Bounded in time (a grandchild could hold the pipe open) and in size
    (only the tail was kept).
    """
    process.wait(timeout=STOP_TIMEOUT_S)
    stderr.join(STOP_TIMEOUT_S)
    detail = stderr.tail().strip()
    if detail:
        return detail
    return f"the overlay exited with status {process.returncode} without explanation"


def printed_controller(
    backend: CursorBackend, spec: str = "file", display: int | None = None, **kwargs
) -> MarkerSourceController:
    """A controller starting on the printed layout named by `spec`."""
    return MarkerSourceController(backend, resolve_layout(spec), display, **kwargs)
