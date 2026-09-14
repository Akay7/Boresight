"""Unit tests for the one-euro filter, driven with an explicit clock.

Every test passes `t` explicitly rather than relying on wall time, so
`dt` is exact and reproducible -- the point of the filter is how it
reacts to `dt`, so that has to be a controlled variable, not incidental
timing noise from the test run itself.
"""

from __future__ import annotations

import math

from boresight.one_euro import OneEuroFilter


def test_the_first_call_returns_its_input_unchanged() -> None:
    filt = OneEuroFilter()

    result = filt.apply((0.3, 0.7), t=0.0)

    assert result == (0.3, 0.7)


def test_a_near_constant_input_stays_close_to_its_mean() -> None:
    filt = OneEuroFilter(min_cutoff=0.5, beta=1.0)
    centre = (0.5, 0.5)
    noise = [(0.01, -0.01), (-0.01, 0.01), (0.008, -0.006), (-0.009, 0.007)]

    outputs = []
    for i, (dx, dy) in enumerate(noise):
        t = i * (1.0 / 30.0)
        point = (centre[0] + dx, centre[1] + dy)
        outputs.append(filt.apply(point, t=t))

    # The raw samples swing by ~0.02 around centre; the filtered ones
    # should be pulled in noticeably closer.
    raw_spread = max(abs(centre[0] + dx - centre[0]) for dx, _ in noise)
    filtered_spread = max(abs(x - centre[0]) for x, _ in outputs[1:])
    assert filtered_spread < raw_spread


def test_a_fast_consistent_ramp_tracks_with_less_lag_than_without_beta() -> None:
    """`beta` is what makes a fast, sustained movement track closely --
    raising the cutoff in proportion to speed rather than leaving it at
    `min_cutoff` regardless. Compare against beta=0 (fixed cutoff) on
    the same ramp, rather than an absolute pixel target, so this does
    not pin the filter's tuned defaults."""
    dt = 1.0 / 30.0
    steps = 30
    # A full-width sweep over one second -- fast and sustained.
    positions = [(i / (steps - 1), 0.5) for i in range(steps)]

    with_beta = OneEuroFilter(min_cutoff=0.5, beta=1.0)
    without_beta = OneEuroFilter(min_cutoff=0.5, beta=0.0)

    with_beta_out = without_beta_out = None
    for i, point in enumerate(positions):
        with_beta_out = with_beta.apply(point, t=i * dt)
        without_beta_out = without_beta.apply(point, t=i * dt)

    with_beta_lag = 1.0 - with_beta_out[0]
    without_beta_lag = 1.0 - without_beta_out[0]
    assert with_beta_lag < without_beta_lag


def test_timing_is_driven_by_a_monotonic_clock_not_call_count() -> None:
    """Feeding the same values at an explicit varying `dt` produces
    different smoothing than feeding them at a fixed `dt`."""
    values = [(0.0, 0.0), (1.0, 0.0), (1.0, 0.0), (1.0, 0.0)]

    fixed = OneEuroFilter(min_cutoff=0.5, beta=1.0)
    fixed_outputs = [fixed.apply(v, t=i * 0.1) for i, v in enumerate(values)]

    varying = OneEuroFilter(min_cutoff=0.5, beta=1.0)
    times = [0.0, 0.05, 0.5, 2.0]
    varying_outputs = [
        varying.apply(v, t=t) for v, t in zip(values, times, strict=True)
    ]

    assert fixed_outputs != varying_outputs


def test_a_large_gap_does_not_overshoot_or_sweep_through_the_middle() -> None:
    """The next value after a gap moves toward the new input at least as
    fast as an equal-dt step earlier in a steady sequence, and never
    past it."""
    filt = OneEuroFilter(min_cutoff=0.5, beta=1.0)
    dt = 1.0 / 30.0

    filt.apply((0.0, 0.0), t=0.0)
    filt.apply((0.0, 0.0), t=dt)
    early_step = filt.apply((0.01, 0.0), t=2 * dt)
    early_progress = early_step[0] - 0.0

    # A big gap, then a jump to a new position far away.
    late_step = filt.apply((1.0, 0.0), t=2 * dt + 5.0)
    late_progress = late_step[0] - 0.0

    # No overshoot: the filtered point never passes the new target.
    assert 0.0 <= late_step[0] <= 1.0
    # At least as much progress toward the target as a normal step.
    assert late_progress >= early_progress or math.isclose(
        late_progress, early_progress
    )
