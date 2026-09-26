"""A zero applied through the pipeline, the dropout hold and a session.

Detection is stubbed with a similarity projection (as in
`test_pipeline.py`), so an image offset of `n` pixels is exactly
`n / SCALE` millimetres on the screen.
"""

from __future__ import annotations

import numpy as np
import pytest

from boresight.aim_hold import HoldingPipeline
from boresight.detect import DetectedMarker
from boresight.inject import FakeCursorBackend
from boresight.marker_map import load_marker_map
from boresight.pipeline import DEFAULT_CONFIG_PATH, AimPipeline
from boresight.zeroing import Zero

IMAGE_SIZE = (1280, 720)
CENTRE_MM = (610.0, 343.0)
SCALE = 0.7
MARKER_MAP = load_marker_map(DEFAULT_CONFIG_PATH)
SCREEN_W, SCREEN_H = MARKER_MAP.screen_size_mm


def _frame() -> np.ndarray:
    return np.zeros((IMAGE_SIZE[1], IMAGE_SIZE[0], 3), dtype=np.uint8)


def _detections(_image) -> list[DetectedMarker]:
    detected = []
    for marker_id, marker in MARKER_MAP.markers.items():
        corners = [
            [
                SCALE * (x - CENTRE_MM[0]) + IMAGE_SIZE[0] / 2,
                SCALE * (y - CENTRE_MM[1]) + IMAGE_SIZE[1] / 2,
            ]
            for x, y in marker.corners_mm()
        ]
        detected.append(DetectedMarker(marker_id, np.array(corners, np.float32)))
    return detected


# 64 px right and 36 px up in a 1280x720 frame.
ZERO = Zero(offset=(0.05, -0.05))
EXPECTED_MM = (CENTRE_MM[0] + 64 / SCALE, CENTRE_MM[1] - 36 / SCALE)


def test_no_zero_is_the_raw_aim() -> None:
    pipeline = AimPipeline(MARKER_MAP, FakeCursorBackend(), detector=_detections)

    plain = pipeline.process_frame(_frame())

    assert plain.aim_point_mm == pytest.approx(CENTRE_MM)
    assert plain.sight is not None and plain.sight.image_size_px == IMAGE_SIZE


def test_a_zero_moves_the_emitted_position_and_the_debug_cursor() -> None:
    backend = FakeCursorBackend()
    pipeline = AimPipeline(MARKER_MAP, backend, detector=_detections)

    result = pipeline.process_frame(_frame(), debug=True, zero=ZERO)

    assert result.aim_point_mm == pytest.approx(EXPECTED_MM)
    expected = (EXPECTED_MM[0] / SCREEN_W, EXPECTED_MM[1] / SCREEN_H)
    assert result.position == pytest.approx(expected)
    assert backend.calls[-1] == pytest.approx(expected)
    assert result.debug.cursor_px == pytest.approx((640 + 64, 360 - 36), abs=0.01)


def test_the_hold_resends_the_corrected_position() -> None:
    backend = FakeCursorBackend()
    detections = [_detections(None), []]
    pipeline = AimPipeline(
        MARKER_MAP, FakeCursorBackend(), detector=lambda _: detections.pop(0)
    )
    holding = HoldingPipeline(pipeline, backend)

    solved = holding.process_frame(_frame(), zero=ZERO)
    holding.process_frame(_frame(), zero=ZERO)

    assert backend.calls == [solved.position, solved.position]
    assert solved.position[0] > CENTRE_MM[0] / SCREEN_W
