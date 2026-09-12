"""A one-euro filter for smoothing a noisy 2D signal over time.

Casiez, Roussel, Vogel, "1€ Filter: A Simple Speed-based Low-pass Filter
for Noisy Input in Interactive Systems" (CHI 2012). Two knobs shape the
result: `min_cutoff` sets how aggressively a *slow-moving* signal is
smoothed (lower cuts more noise but adds more lag), and `beta` raises
the effective cutoff in proportion to how fast the signal is currently
moving, so a fast movement is smoothed less than a slow one instead of
by the same fixed amount.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable

Point = tuple[float, float]


def _smoothing_factor(cutoff: float, dt: float) -> float:
    """The exponential smoothing weight for a low-pass at `cutoff` Hz."""
    time_constant = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + time_constant / dt)


class _LowPassFilter:
    """One exponential low-pass, bootstrapped by its first sample."""

    def __init__(self) -> None:
        self._value: float | None = None

    def apply(self, value: float, alpha: float) -> float:
        if self._value is None:
            self._value = value
        else:
            self._value = alpha * value + (1.0 - alpha) * self._value
        return self._value


class OneEuroFilter:
    """Smooths a stream of 2D points, timestamped by a monotonic clock.

    Each axis is filtered independently, but both share one timestamp
    per update and one derivative-based speed estimate -- the combined
    2D speed, not a per-axis one -- so a fast diagonal movement reads as
    fast on both axes together, rather than only on whichever axis
    happens to be moving faster at that instant.

    The first call bootstraps the filter and returns its input
    unchanged: there is no prior sample to smooth against yet, the same
    way the filter behaves after any other cold start.
    """

    def __init__(
        self,
        min_cutoff: float = 0.5,
        beta: float = 1.0,
        d_cutoff: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._min_cutoff = min_cutoff
        self._beta = beta
        self._d_cutoff = d_cutoff
        self._clock = clock

        self._x_filter = _LowPassFilter()
        self._y_filter = _LowPassFilter()
        self._dx_filter = _LowPassFilter()
        self._dy_filter = _LowPassFilter()

        self._last_point: Point | None = None
        self._last_time: float | None = None

    def apply(self, point: Point, *, t: float | None = None) -> Point:
        """Filter one sample. `t` overrides the clock; tests use this to
        drive an explicit, reproducible `dt` instead of real wall time."""
        now = self._clock() if t is None else t

        if self._last_time is None:
            self._last_point = point
            self._last_time = now
            self._x_filter.apply(point[0], 1.0)
            self._y_filter.apply(point[1], 1.0)
            return point

        # A dropout produces a large dt here, not a special case: as dt
        # grows, the smoothing factor below tends to 1 (see
        # `_smoothing_factor`), so the filter jumps toward the new
        # sample instead of crawling back to it -- and because the
        # factor never exceeds 1, the result is always a point between
        # the old and new value, never an overshoot past it.
        dt = max(now - self._last_time, 1e-9)
        self._last_time = now

        dx_raw = (point[0] - self._last_point[0]) / dt
        dy_raw = (point[1] - self._last_point[1]) / dt
        self._last_point = point

        d_alpha = _smoothing_factor(self._d_cutoff, dt)
        dx = self._dx_filter.apply(dx_raw, d_alpha)
        dy = self._dy_filter.apply(dy_raw, d_alpha)
        speed = math.hypot(dx, dy)

        cutoff = self._min_cutoff + self._beta * speed
        alpha = _smoothing_factor(cutoff, dt)

        x = self._x_filter.apply(point[0], alpha)
        y = self._y_filter.apply(point[1], alpha)
        return (x, y)
