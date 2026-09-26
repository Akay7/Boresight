"""`CaptureClock`: a session's capture timestamps as aim-filter time.

Driven with an explicit server clock, so "the frame arrived late" and
"the client's clock jumped" are controlled inputs.
"""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from boresight.stream import CaptureClock


class _ServerClock:
    def __init__(self, start: float = 100.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def _intervals(stamps: list[float]) -> list[float]:
    return [later - earlier for earlier, later in pairwise(stamps)]


def test_the_first_frame_is_placed_at_the_server_clock() -> None:
    server = _ServerClock(start=42.0)
    clock = CaptureClock(clock=server)

    assert clock.stamp(987654.0) == 42.0


def test_intervals_are_the_capture_intervals_not_the_arrival_intervals() -> None:
    server = _ServerClock()
    clock = CaptureClock(clock=server)
    stamps = []
    # Captured exactly 50 ms apart; arriving 10, 90, 30 and 70 ms apart.
    for client_ms, arrival_gap in [(0, 0), (50, 0.01), (100, 0.09), (150, 0.03)]:
        server.now += arrival_gap
        stamps.append(clock.stamp(1000.0 + client_ms))

    assert _intervals(stamps) == pytest.approx([0.05, 0.05, 0.05])
    assert clock.fallbacks == 0


def test_a_repeated_timestamp_falls_back_to_the_server_interval() -> None:
    server = _ServerClock()
    clock = CaptureClock(clock=server)
    first = clock.stamp(1000.0)
    server.now += 0.04
    second = clock.stamp(1000.0)

    assert second - first == pytest.approx(0.04)
    assert clock.fallbacks == 1


def test_a_fallback_interval_is_never_zero() -> None:
    server = _ServerClock()
    clock = CaptureClock(clock=server)
    first = clock.stamp(1000.0)
    second = clock.stamp(1000.0)  # same server instant too

    assert second - first == pytest.approx(CaptureClock.MIN_STEP_S)


@pytest.mark.parametrize("jump_ms", [-5000.0, -1.0, 1001.0, 3_600_000.0])
def test_a_jump_falls_back_and_the_client_timeline_resumes_after_it(
    jump_ms: float,
) -> None:
    server = _ServerClock()
    clock = CaptureClock(clock=server)
    stamps = [clock.stamp(1000.0)]
    server.now += 0.05
    stamps.append(clock.stamp(1000.0 + jump_ms))
    server.now += 0.2  # arrives late; the client says 50 ms
    stamps.append(clock.stamp(1000.0 + jump_ms + 50.0))

    assert _intervals(stamps) == pytest.approx([0.05, 0.05])
    assert clock.fallbacks == 1


def test_a_long_server_gap_is_clamped_in_the_fallback() -> None:
    server = _ServerClock()
    clock = CaptureClock(clock=server)
    first = clock.stamp(1000.0)
    server.now += 30.0
    second = clock.stamp(1000.0)

    assert second - first == pytest.approx(CaptureClock.MAX_STEP_S)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_a_non_finite_timestamp_is_not_trusted(bad: float) -> None:
    server = _ServerClock()
    clock = CaptureClock(clock=server)
    stamps = [clock.stamp(1000.0)]
    server.now += 0.05
    stamps.append(clock.stamp(bad))
    server.now += 0.05
    # No reference to difference against yet: the server's clock again.
    stamps.append(clock.stamp(1100.0))
    server.now += 0.3
    stamps.append(clock.stamp(1150.0))

    assert _intervals(stamps) == pytest.approx([0.05, 0.05, 0.05])
    assert all(math.isfinite(stamp) for stamp in stamps)


def test_two_sessions_do_not_share_a_timeline() -> None:
    server = _ServerClock()
    phone = CaptureClock(clock=server)
    camera = CaptureClock(clock=server)
    phone_stamps = [phone.stamp(5_000_000.0)]
    camera_stamps = [camera.stamp(12.0)]
    server.now += 0.05
    phone_stamps.append(phone.stamp(5_000_033.0))
    camera_stamps.append(camera.stamp(112.0))

    assert _intervals(phone_stamps) == pytest.approx([0.033])
    assert _intervals(camera_stamps) == pytest.approx([0.1])
    assert phone.fallbacks == camera.fallbacks == 0
