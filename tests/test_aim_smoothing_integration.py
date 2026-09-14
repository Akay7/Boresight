"""Integration tests: a real `AimPipeline`, wired through the same
`SmoothingCursorBackend` wrapping `MarkerSourceController` uses, driven
by a stub detector so the aim point is exactly controlled.

Detection is stubbed the same way `test_pipeline.py` stubs it -- the
point here is the smoothing layered on top of a real solve, not
detection itself.
"""

from __future__ import annotations

import numpy as np
import pytest

from boresight.detect import DetectedMarker
from boresight.inject import FakeCursorBackend, SmoothingCursorBackend
from boresight.marker_map import MarkerMap, load_marker_map
from boresight.overlay.layout import overlay_layout
from boresight.pipeline import DEFAULT_CONFIG_PATH, AimPipeline

IMAGE_SIZE = (1280, 720)
SCALE_PX_PER_MM = 0.7


@pytest.fixture(scope="module")
def printed_map() -> MarkerMap:
    return load_marker_map(DEFAULT_CONFIG_PATH)


@pytest.fixture(scope="module")
def screen_map() -> MarkerMap:
    # A different layout entirely -- different screen size, different
    # marker placement -- the way switching to on-screen markers
    # actually produces one, so a shared aim point exercises the same
    # renormalization a real switch does.
    return overlay_layout((1920, 1080))


def _frame() -> np.ndarray:
    return np.zeros((IMAGE_SIZE[1], IMAGE_SIZE[0], 3), dtype=np.uint8)


def _project(point_mm: tuple[float, float], centre_mm: tuple[float, float]) -> list:
    return [
        SCALE_PX_PER_MM * (point_mm[0] - centre_mm[0]) + IMAGE_SIZE[0] / 2.0,
        SCALE_PX_PER_MM * (point_mm[1] - centre_mm[1]) + IMAGE_SIZE[1] / 2.0,
    ]


def _detections(
    marker_map: MarkerMap, centre_mm: tuple[float, float]
) -> list[DetectedMarker]:
    detected = []
    for marker_id in (0, 1, 2, 3):
        corners_mm = marker_map.markers[marker_id].corners_mm()
        corners_px = np.array(
            [_project(corner, centre_mm) for corner in corners_mm], dtype=np.float32
        )
        detected.append(DetectedMarker(marker_id=marker_id, corners=corners_px))
    return detected


def test_small_frame_to_frame_noise_is_attenuated_by_the_wrapped_backend(
    printed_map: MarkerMap,
) -> None:
    raw_backend = FakeCursorBackend()
    wrapped = SmoothingCursorBackend(raw_backend)
    current: dict = {"detections": []}
    pipeline = AimPipeline(
        printed_map, wrapped, detector=lambda _f: current["detections"]
    )

    width_mm, height_mm = printed_map.screen_size_mm
    centre_mm = (width_mm / 2.0, height_mm / 2.0)
    # Small, noise-scale jitter around a fixed centre -- the "holding
    # aim on a steady target" case.
    jitter_mm = [
        (0.0, 0.0),
        (3.0, -2.0),
        (-2.0, 3.0),
        (2.0, -3.0),
        (-3.0, 2.0),
        (1.0, -1.0),
    ]

    raw_positions = []
    for dx, dy in jitter_mm:
        point_mm = (centre_mm[0] + dx, centre_mm[1] + dy)
        current["detections"] = _detections(printed_map, point_mm)
        result = pipeline.process_frame(_frame())
        raw_positions.append(result.position)

    def _variance(points: list[tuple[float, float]]) -> float:
        mean_x = sum(p[0] for p in points) / len(points)
        mean_y = sum(p[1] for p in points) / len(points)
        return sum((p[0] - mean_x) ** 2 + (p[1] - mean_y) ** 2 for p in points) / len(
            points
        )

    assert len(raw_backend.calls) == len(jitter_mm)
    assert _variance(raw_backend.calls) < _variance(raw_positions)


def test_a_marker_source_switch_with_the_same_aim_point_is_not_a_discontinuity(
    printed_map: MarkerMap, screen_map: MarkerMap
) -> None:
    """Mirrors how `MarkerSourceController` wires things: one wrapped
    backend, a fresh `AimPipeline` per marker source. Aiming at the same
    normalized position (screen centre) before and after a switch should
    not itself introduce a jump, beyond ordinary per-frame noise."""
    raw_backend = FakeCursorBackend()
    wrapped = SmoothingCursorBackend(raw_backend)

    printed_centre_mm = tuple(v / 2.0 for v in printed_map.screen_size_mm)
    screen_centre_mm = tuple(v / 2.0 for v in screen_map.screen_size_mm)

    printed_pipeline = AimPipeline(
        printed_map,
        wrapped,
        detector=lambda _f: _detections(printed_map, printed_centre_mm),
    )
    screen_pipeline = AimPipeline(
        screen_map,
        wrapped,
        detector=lambda _f: _detections(screen_map, screen_centre_mm),
    )

    # A few frames on printed markers, aimed at centre...
    for _ in range(4):
        printed_pipeline.process_frame(_frame())
    before_switch = raw_backend.calls[-1]

    # ...the switch itself (a fresh pipeline, same wrapped backend)...
    screen_pipeline.process_frame(_frame())
    right_after_switch = raw_backend.calls[-1]

    # ...and a few more frames on the new source, still aimed at centre.
    for _ in range(4):
        screen_pipeline.process_frame(_frame())

    # Both sides are aiming at (0.5, 0.5) normalized; the step across
    # the switch should be no larger than ordinary steps either side of
    # it, not a jump introduced by the switch itself.
    def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    switch_step = _dist(before_switch, right_after_switch)
    later_step = _dist(raw_backend.calls[-2], raw_backend.calls[-1])

    assert switch_step == pytest.approx(later_step, abs=0.01)
