"""Unit tests for the per-frame pipeline.

Detection is stubbed here. The point is to drive the pipeline's policy
branches -- unmapped IDs, off-panel aim, dropout, poor conditioning --
directly, rather than hunting for a rendered image that happens to
produce each one. Those same branches are exercised against real
detection on real fixtures in `test_pipeline_e2e.py`.
"""

from __future__ import annotations

import dataclasses
import json

import numpy as np
import pytest

from boresight.detect import DetectedMarker
from boresight.inject import FakeCursorBackend
from boresight.marker_map import MarkerMap, load_marker_map
from boresight.pipeline import (
    DEFAULT_CONFIG_PATH,
    EDGE_MARGIN,
    AimPipeline,
    FrameOutcome,
)

IMAGE_SIZE = (1280, 720)
PANEL_CENTRE_MM = (610.0, 343.0)

# Scale for the synthetic screen-mm -> image-px projection below. 0.7
# puts the whole marker layout (1460mm across) inside a 1280px frame
# with room to spare, so no synthetic corner lands off-image.
SCALE_PX_PER_MM = 0.7


@pytest.fixture(scope="module")
def marker_map() -> MarkerMap:
    return load_marker_map(DEFAULT_CONFIG_PATH)


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
    """Aiming past the edge is ordinary; the cursor should sit near the
    edge rather than freeze. But clamped output is otherwise
    indistinguishable from an aim at the near-edge margin, so say so."""
    off_panel_mm = (-250.0, 900.0)
    pipeline = _pipeline(
        marker_map, backend, _detections(marker_map, [0, 1, 2, 3], off_panel_mm)
    )

    result = pipeline.process_frame(_frame())

    expected = (EDGE_MARGIN, 1.0 - EDGE_MARGIN)
    assert result.outcome is FrameOutcome.SOLVED
    assert result.clamped
    assert result.position == pytest.approx(expected, abs=1e-6)
    assert backend.calls[0] == pytest.approx(expected, abs=1e-6)
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


# --- Debug geometry --------------------------------------------------


def test_debug_is_absent_unless_asked_for_and_changes_nothing(
    marker_map, backend
) -> None:
    """The debug path must be a pure addition. If asking for it could
    change the answer, every reading taken through it would describe a
    different pipeline than the one that moves the cursor."""
    pipeline = _pipeline(marker_map, backend, _detections(marker_map, [0, 1, 2, 3]))
    frame = _frame()

    plain = pipeline.process_frame(frame)
    instrumented = pipeline.process_frame(frame, debug=True)

    assert plain.debug is None
    assert instrumented.debug is not None
    # Every other field, compared field-for-field.
    assert dataclasses.replace(instrumented, debug=None) == plain


def test_debug_reports_each_detection_where_it_sat_in_the_image(
    marker_map, backend
) -> None:
    detected = _detections(marker_map, [0, 1, 2, 3])
    pipeline = _pipeline(marker_map, backend, detected)

    debug = pipeline.process_frame(_frame(), debug=True).debug

    assert debug.image_size_px == IMAGE_SIZE
    assert len(debug.markers) == 4
    assert [marker.marker_id for marker in debug.markers] == [0, 1, 2, 3]
    for reported, source in zip(debug.markers, detected, strict=True):
        assert reported.mapped
        assert reported.corners_px == pytest.approx(
            [tuple(corner) for corner in source.corners], abs=1e-3
        )


def test_debug_reports_an_unmapped_marker_as_seen_but_ignored(
    marker_map, backend
) -> None:
    """The distinction the counts cannot draw: a tag being seen and
    skipped looks identical to one not being seen at all."""
    detected = _detections(marker_map, [0, 1, 2, 3])
    stray = _detections(marker_map, [5])[0]
    stray.marker_id = 49
    detected.append(stray)
    pipeline = _pipeline(marker_map, backend, detected)

    debug = pipeline.process_frame(_frame(), debug=True).debug

    assert len(debug.markers) == 5
    ignored = [marker for marker in debug.markers if not marker.mapped]
    assert [marker.marker_id for marker in ignored] == [49]


def test_debug_on_a_frame_with_no_detections_is_empty_not_absent(
    marker_map, backend
) -> None:
    """`None` means "not requested". A frame that saw nothing has
    something to say -- that it saw nothing -- and says it."""
    pipeline = _pipeline(marker_map, backend, [])

    result = pipeline.process_frame(_frame(), debug=True)

    assert result.outcome is FrameOutcome.NO_MARKERS
    assert result.debug is not None
    assert result.debug.markers == ()
    assert result.debug.image_size_px == IMAGE_SIZE
    assert result.debug.screen_quad_px is None
    assert result.debug.cursor_px is None


def test_the_projected_screen_quad_recovers_the_configured_screen(
    marker_map, backend
) -> None:
    """Drawn over the preview, this outline is claimed to be the panel.
    Taken back through the homography it must be exactly the configured
    screen rectangle -- corners, order and all."""
    pipeline = _pipeline(marker_map, backend, _detections(marker_map, [0, 1, 2, 3]))

    result = pipeline.process_frame(_frame(), debug=True)

    width_mm, height_mm = marker_map.screen_size_mm
    quad_px = np.array(result.debug.screen_quad_px, dtype=np.float64).reshape(-1, 1, 2)
    # The synthetic projection is a similarity transform of scale
    # SCALE_PX_PER_MM about the panel centre, so invert it directly
    # rather than re-deriving a homography the test would then be
    # checking against itself.
    recovered = []
    for x, y in quad_px[:, 0, :]:
        recovered.append(
            float((x - IMAGE_SIZE[0] / 2.0) / SCALE_PX_PER_MM + PANEL_CENTRE_MM[0])
        )
        recovered.append(
            float((y - IMAGE_SIZE[1] / 2.0) / SCALE_PX_PER_MM + PANEL_CENTRE_MM[1])
        )

    # Clockwise from the top-left, matching `Marker.corners_mm`.
    assert recovered == pytest.approx(
        [0.0, 0.0, width_mm, 0.0, width_mm, height_mm, 0.0, height_mm],
        abs=1e-2,
    )


def test_the_drawn_cursor_is_the_emitted_position_not_the_aim_point(
    marker_map, backend
) -> None:
    """The point of the whole change. An aim point pushed back through
    its own homography returns the image centre by construction, so it
    could never disagree with the reticle and would test nothing. The
    emitted position has been normalized, clamped and rounded on the way
    out; carrying *that* back is what can disagree."""
    centred = _pipeline(marker_map, backend, _detections(marker_map, [0, 1, 2, 3]))
    image_centre = (IMAGE_SIZE[0] / 2.0, IMAGE_SIZE[1] / 2.0)

    on_panel = centred.process_frame(_frame(), debug=True)

    assert not on_panel.clamped
    assert on_panel.debug.cursor_px == pytest.approx(image_centre, abs=0.5)

    # Aiming well past the edge: the emitted position is clamped to the
    # margin, so the drawn cursor must part company with the reticle.
    off_panel = _pipeline(
        marker_map, backend, _detections(marker_map, [0, 1, 2, 3], (-250.0, 900.0))
    ).process_frame(_frame(), debug=True)

    assert off_panel.clamped
    assert off_panel.debug.cursor_px != pytest.approx(image_centre, abs=5.0)


def test_an_unsolved_frame_reports_detections_but_no_projection(
    marker_map, backend
) -> None:
    """Nothing may be carried over from a frame that did solve: this is
    drawn over a live image, where a stale outline is a confident lie."""
    stray = _detections(marker_map, [0])
    stray[0].marker_id = 49
    pipeline = _pipeline(marker_map, backend, stray)

    result = pipeline.process_frame(_frame(), debug=True)

    assert result.outcome is FrameOutcome.INSUFFICIENT_CORRESPONDENCES
    assert len(result.debug.markers) == 1
    assert result.debug.markers[0].mapped is False
    assert result.debug.screen_quad_px is None
    assert result.debug.cursor_px is None
    assert result.debug.reprojection_error_max_px is None
    assert result.debug.reprojection_error_mean_px is None


def test_a_well_fitted_solve_reports_a_small_reprojection_error(
    marker_map, backend
) -> None:
    pipeline = _pipeline(marker_map, backend, _detections(marker_map, [0, 1, 2, 3]))

    debug = pipeline.process_frame(_frame(), debug=True).debug

    assert debug.reprojection_error_max_px < 1.0
    assert debug.reprojection_error_mean_px <= debug.reprojection_error_max_px


def test_the_debug_message_rounds_and_names_every_field(marker_map, backend) -> None:
    """This is the wire payload the phone draws from."""
    pipeline = _pipeline(marker_map, backend, _detections(marker_map, [0, 1, 2, 3]))

    message = pipeline.process_frame(_frame(), debug=True).debug.as_message()

    assert message["image_px"] == list(IMAGE_SIZE)
    assert len(message["markers"]) == 4
    assert message["markers"][0]["id"] == 0
    assert message["markers"][0]["mapped"] is True
    assert len(message["markers"][0]["corners_px"]) == 4
    assert len(message["screen_quad_px"]) == 4
    assert message["cursor_px"] == pytest.approx(
        [IMAGE_SIZE[0] / 2.0, IMAGE_SIZE[1] / 2.0], abs=0.5
    )
    # Serializable as-is: it rides the existing telemetry message.
    assert json.loads(json.dumps(message)) == message
