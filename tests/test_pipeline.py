"""Unit tests for the per-frame pipeline.

Detection is stubbed here. The point is to drive the pipeline's policy
branches -- unmapped IDs, off-panel aim, dropout, poor conditioning --
directly, rather than hunting for a rendered image that happens to
produce each one. Those same branches are exercised against real
detection on real fixtures in `test_pipeline_e2e.py`.
"""

from __future__ import annotations

import numpy as np
import pytest

from boresight.detect import DetectedMarker
from boresight.inject import FakeCursorBackend
from boresight.marker_map import MarkerMap, load_marker_map
from boresight.pipeline import AimPipeline, FrameOutcome

CONFIG_PATH = "config/markers.toml"
IMAGE_SIZE = (1280, 720)
PANEL_CENTRE_MM = (610.0, 343.0)

# Scale for the synthetic screen-mm -> image-px projection below. 0.7
# puts the whole marker layout (1460mm across) inside a 1280px frame
# with room to spare, so no synthetic corner lands off-image.
SCALE_PX_PER_MM = 0.7


@pytest.fixture(scope="module")
def marker_map() -> MarkerMap:
    return load_marker_map(CONFIG_PATH)


@pytest.fixture
def backend() -> FakeCursorBackend:
    return FakeCursorBackend()


def _frame() -> np.ndarray:
    """A frame the stub detector ignores. Only its shape is read, to give
    the solver the image centre it maps back to screen space."""
    return np.zeros((IMAGE_SIZE[1], IMAGE_SIZE[0], 3), dtype=np.uint8)


def _project(point_mm: tuple[float, float], centre_mm: tuple[float, float]) -> list:
    """Screen mm -> image px, such that `centre_mm` lands at the image centre.

    A similarity transform, so the aim point the solver recovers from
    these correspondences is exactly `centre_mm` -- which makes it the
    knob every test below turns.
    """
    return [
        SCALE_PX_PER_MM * (point_mm[0] - centre_mm[0]) + IMAGE_SIZE[0] / 2.0,
        SCALE_PX_PER_MM * (point_mm[1] - centre_mm[1]) + IMAGE_SIZE[1] / 2.0,
    ]


def _detections(
    marker_map: MarkerMap,
    marker_ids: list[int],
    centre_mm: tuple[float, float] = PANEL_CENTRE_MM,
) -> list[DetectedMarker]:
    detected = []
    for marker_id in marker_ids:
        corners_mm = marker_map.markers[marker_id].corners_mm()
        corners_px = np.array(
            [_project(corner, centre_mm) for corner in corners_mm], dtype=np.float32
        )
        detected.append(DetectedMarker(marker_id=marker_id, corners=corners_px))
    return detected


def _pipeline(
    marker_map: MarkerMap, backend: FakeCursorBackend, detected: list
) -> AimPipeline:
    return AimPipeline(marker_map, backend, detector=lambda _frame: detected)


# --- Emission path ---------------------------------------------------


def test_a_solvable_frame_emits_exactly_one_move(marker_map, backend) -> None:
    pipeline = _pipeline(marker_map, backend, _detections(marker_map, [0, 1, 2, 3]))

    result = pipeline.process_frame(_frame())

    assert result.outcome is FrameOutcome.SOLVED
    assert result.emitted
    assert len(backend.calls) == 1
    assert result.markers_detected == 4
    assert result.markers_mapped == 4
    assert result.markers_ignored == 0


def test_screen_centre_normalizes_to_the_midpoint(marker_map, backend) -> None:
    pipeline = _pipeline(
        marker_map, backend, _detections(marker_map, [0, 1, 2, 3], PANEL_CENTRE_MM)
    )

    result = pipeline.process_frame(_frame())

    assert result.position == pytest.approx((0.5, 0.5), abs=1e-6)
    assert backend.calls[0] == pytest.approx((0.5, 0.5), abs=1e-6)
    assert not result.clamped


def test_normalization_uses_the_configured_screen_size(marker_map, backend) -> None:
    """Not the frame, not the marker extent, not the backend. A quarter
    of the way across the panel is 0.25 regardless of what else changes."""
    quarter_mm = (610.0 / 2.0, 343.0 / 2.0)
    pipeline = _pipeline(
        marker_map, backend, _detections(marker_map, [0, 1, 2, 3], quarter_mm)
    )

    result = pipeline.process_frame(_frame())

    assert result.position == pytest.approx((0.25, 0.25), abs=1e-6)


def test_processing_the_same_frame_twice_is_identical(marker_map, backend) -> None:
    """Stateless: the second call must not be influenced by the first."""
    pipeline = _pipeline(marker_map, backend, _detections(marker_map, [0, 1, 2, 3]))
    frame = _frame()

    first = pipeline.process_frame(frame)
    second = pipeline.process_frame(frame)

    assert first == second
    assert len(backend.calls) == 2
    assert backend.calls[0] == backend.calls[1]


def test_a_colour_frame_and_its_greyscale_agree(marker_map, backend) -> None:
    """The pipeline converts to greyscale itself, so callers holding a
    camera's colour frame need not."""
    pipeline = _pipeline(marker_map, backend, _detections(marker_map, [0, 1, 2, 3]))

    colour = pipeline.process_frame(_frame())
    grey = pipeline.process_frame(np.zeros(IMAGE_SIZE[::-1], dtype=np.uint8))

    assert colour == grey


# --- No-emission paths -----------------------------------------------


def test_no_detected_markers_emits_nothing(marker_map, backend) -> None:
    pipeline = _pipeline(marker_map, backend, [])

    result = pipeline.process_frame(_frame())

    assert result.outcome is FrameOutcome.NO_MARKERS
    assert not result.emitted
    assert backend.calls == []
    assert result.aim_point_mm is None
    assert result.position is None


def test_too_few_correspondences_emits_nothing(marker_map, backend) -> None:
    """Every detection is unmapped, so nothing reaches the solver. The
    solver's error is converted to an outcome rather than propagating:
    dropout is the steady state, not an exception."""
    stray = _detections(marker_map, [0])
    stray[0].marker_id = 49
    pipeline = _pipeline(marker_map, backend, stray)

    result = pipeline.process_frame(_frame())

    assert result.outcome is FrameOutcome.INSUFFICIENT_CORRESPONDENCES
    assert backend.calls == []
    assert result.markers_detected == 1
    assert result.markers_mapped == 0
    assert result.markers_ignored == 1


def test_degenerate_correspondences_emit_nothing(marker_map, backend) -> None:
    """Four coincident corners cannot define a homography. The solver
    refuses; the pipeline reports it rather than crashing the frame."""
    collapsed = np.zeros((4, 2), dtype=np.float32)
    pipeline = _pipeline(
        marker_map, backend, [DetectedMarker(marker_id=0, corners=collapsed)]
    )

    result = pipeline.process_frame(_frame())

    assert result.outcome is FrameOutcome.SOLVE_FAILED
    assert backend.calls == []


# --- Policy paths ----------------------------------------------------


def test_an_unmapped_marker_is_ignored_and_the_frame_still_solves(
    marker_map, backend
) -> None:
    detected = _detections(marker_map, [0, 1, 2, 3])
    stray = _detections(marker_map, [5])[0]
    stray.marker_id = 49
    detected.append(stray)
    pipeline = _pipeline(marker_map, backend, detected)

    result = pipeline.process_frame(_frame())

    assert result.outcome is FrameOutcome.SOLVED
    assert result.markers_detected == 5
    assert result.markers_mapped == 4
    assert result.markers_ignored == 1
    # The stray contributed nothing, so the answer is the four-corner one.
    assert result.position == pytest.approx((0.5, 0.5), abs=1e-6)


def test_an_off_panel_aim_point_is_clamped_and_reported(marker_map, backend) -> None:
    """Aiming past the edge is ordinary; the cursor should sit at the
    edge rather than freeze. But clamped output is otherwise
    indistinguishable from an aim at the exact edge, so say so."""
    off_panel_mm = (-250.0, 900.0)
    pipeline = _pipeline(
        marker_map, backend, _detections(marker_map, [0, 1, 2, 3], off_panel_mm)
    )

    result = pipeline.process_frame(_frame())

    assert result.outcome is FrameOutcome.SOLVED
    assert result.clamped
    assert result.position == pytest.approx((0.0, 1.0), abs=1e-6)
    assert backend.calls[0] == pytest.approx((0.0, 1.0), abs=1e-6)
    # The unclamped truth survives, which is the whole point.
    assert result.aim_point_mm == pytest.approx(off_panel_mm, abs=1e-3)


def test_a_flagged_solve_is_emitted_with_its_conditioning(marker_map, backend) -> None:
    """A single marker fits exactly and tells you nothing about the aim
    point 700mm away. Emit it anyway -- flagged does not mean wrong, and
    suppressing would blank the cursor in exactly the close-range case
    the midpoint markers exist to serve -- but report the flag."""
    pipeline = _pipeline(marker_map, backend, _detections(marker_map, [0]))

    result = pipeline.process_frame(_frame())

    assert result.outcome is FrameOutcome.SOLVED
    assert len(backend.calls) == 1
    assert result.aim_point_inside_hull is False
    assert result.aim_point_hull_distance_mm < 0.0


def test_a_well_conditioned_solve_is_reported_as_such(marker_map, backend) -> None:
    pipeline = _pipeline(marker_map, backend, _detections(marker_map, [0, 1, 2, 3]))

    result = pipeline.process_frame(_frame())

    assert result.aim_point_inside_hull is True
    assert result.aim_point_hull_distance_mm > 0.0
