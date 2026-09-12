"""Unit tests for `HoldingPipeline`, driven with an explicit clock and a
stub detector -- the same pattern `test_pipeline.py` uses, so a "solved"
or "not solved" frame is a controlled input rather than something
hunted for in a rendered image.
"""

from __future__ import annotations

import numpy as np
import pytest

from boresight.aim_hold import HoldingPipeline
from boresight.detect import DetectedMarker
from boresight.inject import FakeCursorBackend, SmoothingCursorBackend
from boresight.marker_map import MarkerMap, load_marker_map
from boresight.pipeline import DEFAULT_CONFIG_PATH, AimPipeline, FrameOutcome

IMAGE_SIZE = (1280, 720)
PANEL_CENTRE_MM = (610.0, 343.0)
SCALE_PX_PER_MM = 0.7


@pytest.fixture(scope="module")
def marker_map() -> MarkerMap:
    return load_marker_map(DEFAULT_CONFIG_PATH)


def _frame() -> np.ndarray:
    return np.zeros((IMAGE_SIZE[1], IMAGE_SIZE[0], 3), dtype=np.uint8)


def _project(point_mm: tuple[float, float], centre_mm: tuple[float, float]) -> list:
    return [
        SCALE_PX_PER_MM * (point_mm[0] - centre_mm[0]) + IMAGE_SIZE[0] / 2.0,
        SCALE_PX_PER_MM * (point_mm[1] - centre_mm[1]) + IMAGE_SIZE[1] / 2.0,
    ]


def _detections(marker_map: MarkerMap, centre_mm: tuple[float, float]) -> list:
    detected = []
    for marker_id in (0, 1, 2, 3):
        corners_mm = marker_map.markers[marker_id].corners_mm()
        corners_px = np.array(
            [_project(corner, centre_mm) for corner in corners_mm], dtype=np.float32
        )
        detected.append(DetectedMarker(marker_id=marker_id, corners=corners_px))
    return detected


def _pipeline(marker_map: MarkerMap, backend, solves: list) -> AimPipeline:
    """`solves` holds the detections to return per call, popped in order.
    An empty entry means an unsolvable frame (no markers detected)."""

    def detect(_frame):
        return solves.pop(0)

    return AimPipeline(marker_map, backend, detector=detect)


def test_a_solved_frame_passes_through_untouched(marker_map: MarkerMap) -> None:
    backend = FakeCursorBackend()
    inner = _pipeline(marker_map, backend, [_detections(marker_map, PANEL_CENTRE_MM)])
    times = iter([0.0])
    holding = HoldingPipeline(inner, backend, clock=lambda: next(times))

    result = holding.process_frame(_frame())

    assert result.outcome is FrameOutcome.SOLVED
    assert backend.calls == [result.position]


def test_a_non_solved_frame_within_the_window_resends_the_last_position(
    marker_map: MarkerMap,
) -> None:
    backend = FakeCursorBackend()
    inner = _pipeline(
        marker_map, backend, [_detections(marker_map, PANEL_CENTRE_MM), []]
    )
    times = iter([0.0, 0.2])
    holding = HoldingPipeline(inner, backend, hold_s=0.75, clock=lambda: next(times))

    solved = holding.process_frame(_frame())
    unsolved = holding.process_frame(_frame())

    assert unsolved.outcome is FrameOutcome.NO_MARKERS
    assert unsolved.position is None  # the real result is untouched
    assert backend.calls == [solved.position, solved.position]


def test_a_non_solved_frame_past_the_window_is_not_held(marker_map: MarkerMap) -> None:
    backend = FakeCursorBackend()
    inner = _pipeline(
        marker_map, backend, [_detections(marker_map, PANEL_CENTRE_MM), []]
    )
    times = iter([0.0, 10.0])
    holding = HoldingPipeline(inner, backend, hold_s=0.75, clock=lambda: next(times))

    solved = holding.process_frame(_frame())
    holding.process_frame(_frame())

    assert backend.calls == [solved.position]


def test_a_new_solve_mid_hold_replaces_the_held_position(marker_map: MarkerMap) -> None:
    other_centre_mm = (610.0 / 2.0, 343.0 / 2.0)
    backend = FakeCursorBackend()
    inner = _pipeline(
        marker_map,
        backend,
        [
            _detections(marker_map, PANEL_CENTRE_MM),
            _detections(marker_map, other_centre_mm),
            [],
        ],
    )
    times = iter([0.0, 0.1, 0.2])
    holding = HoldingPipeline(inner, backend, hold_s=0.75, clock=lambda: next(times))

    holding.process_frame(_frame())
    second = holding.process_frame(_frame())
    holding.process_frame(_frame())

    # The final held resend matches the second (most recent) solve, not
    # the first.
    assert backend.calls[-1] == second.position
    assert second.position != pytest.approx((0.5, 0.5), abs=1e-6)


def test_holding_is_a_no_op_through_a_real_smoothing_filter(
    marker_map: MarkerMap,
) -> None:
    """The whole point: re-sending an unchanged value through a real
    one-euro filter cannot introduce a jump, no matter how large a `dt`
    the resend carries."""
    raw = FakeCursorBackend()
    backend = SmoothingCursorBackend(raw)
    inner = _pipeline(
        marker_map, backend, [_detections(marker_map, PANEL_CENTRE_MM), []]
    )
    times = iter([0.0, 5.0])  # a large gap before the held resend
    holding = HoldingPipeline(inner, backend, hold_s=10.0, clock=lambda: next(times))

    holding.process_frame(_frame())
    holding.process_frame(_frame())

    # Exact algebraically; allow for floating-point rounding in the
    # filter's own arithmetic, which is not exact bit-for-bit.
    assert raw.calls[0] == pytest.approx(raw.calls[1], abs=1e-9)
