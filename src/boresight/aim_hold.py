"""Keeping the cursor backend alive through a brief detection dropout.

`AimPipeline.process_frame` (`pipeline.py`) only calls
`backend.move_absolute` on a solved frame; on any other outcome it goes
silent. On this platform that silence reads as the OS cursor going idle
-- a Wayland compositor hides a pointer that produces no events for a
while, and a short run of unsolved frames (a marker briefly occluded,
motion blur) is ordinary, not a real loss of aim. `HoldingPipeline`
composes around an `AimPipeline` to re-send its last solved position to
the backend through a short run of unsolved frames, without moving the
cursor or changing what solving itself reports -- and stops once the
gap runs longer than an ordinary dropout, so aim is not held stale
forever.

Deliberately a wrapper, not a change to `AimPipeline`: the pipeline's
own spec requires it to stay stateless, and this needs to remember the
last solved position across calls to do its job.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np

from boresight.inject import CursorBackend
from boresight.pipeline import AimPipeline, FrameOutcome, FrameResult

# How long to keep re-sending the last solved position after the frames
# stop solving. Picked by feel, not measurement -- see the change's
# design notes. Short enough that a held position is never far from
# reality; long enough to outlast an ordinary brief dropout.
DEFAULT_HOLD_S = 0.75


class HoldingPipeline:
    """Wraps an `AimPipeline`, holding its last solved position alive on
    the cursor backend through a brief run of unsolved frames.

    `process_frame` always returns exactly what the wrapped pipeline
    returned -- holding is an effect on the cursor backend only, never
    on what a caller sees. The wire report and any debug overlay a
    caller builds from that result are therefore unaffected by holding.
    """

    def __init__(
        self,
        pipeline: AimPipeline,
        backend: CursorBackend,
        hold_s: float = DEFAULT_HOLD_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._pipeline = pipeline
        self._backend = backend
        self._hold_s = hold_s
        self._clock = clock

        self._last_position: tuple[float, float] | None = None
        self._last_time: float | None = None

    def process_frame(self, frame: np.ndarray, *, debug: bool = False) -> FrameResult:
        result = self._pipeline.process_frame(frame, debug=debug)
        now = self._clock()

        if result.outcome is FrameOutcome.SOLVED:
            self._last_position = result.position
            self._last_time = now
        elif (
            self._last_position is not None
            and self._last_time is not None
            and (now - self._last_time) <= self._hold_s
        ):
            # Re-sent verbatim: through a `SmoothingCursorBackend`, an
            # unchanged value is algebraically a no-op regardless of
            # the `dt` this call carries (the filter converges to
            # exactly the value it is already holding), modulo
            # floating-point rounding far below anything visible -- so
            # this cannot introduce a jump, only fresh device traffic.
            self._backend.move_absolute(*self._last_position)

        return result
