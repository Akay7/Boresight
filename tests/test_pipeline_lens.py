"""Lens correction in the aim pipeline, on a layout rendered through a
known distorted camera.

The shipped marker layout is drawn onto a canvas (1 px == 1 mm), placed
on the plane, imaged by `lens_render`'s camera and distorted. Ground
truth is exact: the frame's centre pixel looks along the ray that the
true lens undistorts it to, and that ray meets the plane at a point the
true plane homography gives directly.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from lens_render import (
    CAMERA_MATRIX,
    DIST_COEFFS,
    IMAGE_SIZE,
    distortion_maps,
    plane_homography,
    render,
)

from boresight.detect import DICTIONARY
from boresight.inject import FakeCursorBackend
from boresight.lens import LensModel
from boresight.marker_map import MarkerMap, load_marker_map
from boresight.pipeline import DEFAULT_CONFIG_PATH, AimPipeline, FrameOutcome
from boresight.zeroing import Zero

# Canvas origin in screen mm: markers sit up to 120mm outside the panel.
CANVAS_ORIGIN_MM = (-150.0, -150.0)

# Poses 1.15-1.2m from the layout with all eight markers in view, the
# outer ones near the frame edges where the distortion is ~25px.
POSES = [
    (np.array([0.0, 0.0, 0.0]), np.array([-610.0, -343.0, 1150.0])),
    (np.array([0.0, -0.1, 0.0]), np.array([-580.0, -343.0, 1200.0])),
    (np.array([-0.06, -0.06, -0.05]), np.array([-600.0, -360.0, 1180.0])),
]

TRUE_LENS = LensModel(CAMERA_MATRIX, DIST_COEFFS, IMAGE_SIZE)

# Observed: 11.0, 15.9 and 42.5mm without the lens; 0.42, 0.61 and
# 0.64mm with it. The bound is ~3x the corrected worst case and far
# below every uncorrected one.
CORRECTED_BOUND_MM = 2.0


@pytest.fixture(scope="module")
def marker_map() -> MarkerMap:
    return load_marker_map(DEFAULT_CONFIG_PATH)


@pytest.fixture(scope="module")
def maps():
    return distortion_maps()


def _canvas(marker_map: MarkerMap) -> np.ndarray:
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICTIONARY))
    width, height = marker_map.screen_size_mm
    ox, oy = CANVAS_ORIGIN_MM
    canvas = np.full((int(height - 2 * oy), int(width - 2 * ox)), 255, np.uint8)
    for marker in marker_map.markers.values():
        size = int(marker.size_mm)
        tag = cv2.aruco.generateImageMarker(dictionary, marker.marker_id, size)
        x, y = int(marker.x_mm - ox), int(marker.y_mm - oy)
        canvas[y : y + size, x : x + size] = tag
    return canvas


def _canvas_to_plane() -> np.ndarray:
    ox, oy = CANVAS_ORIGIN_MM
    return np.array([[1.0, 0.0, ox], [0.0, 1.0, oy], [0.0, 0.0, 1.0]])


def _true_aim_mm(plane_to_ideal: np.ndarray) -> tuple[float, float]:
    centre = TRUE_LENS.undistort_point((IMAGE_SIZE[0] / 2, IMAGE_SIZE[1] / 2))
    point = np.linalg.inv(plane_to_ideal) @ np.array([*centre, 1.0])
    return float(point[0] / point[2]), float(point[1] / point[2])


def _errors(marker_map, maps, lens):
    errors = []
    for rvec, tvec in POSES:
        plane_to_ideal = plane_homography(rvec, tvec)
        frame = render(_canvas(marker_map), plane_to_ideal @ _canvas_to_plane(), maps)
        result = AimPipeline(marker_map, FakeCursorBackend()).process_frame(
            frame, lens=lens
        )
        assert result.outcome is FrameOutcome.SOLVED
        assert result.markers_mapped == 8
        error = np.subtract(result.aim_point_mm, _true_aim_mm(plane_to_ideal))
        errors.append(float(np.linalg.norm(error)))
    return errors


def test_lens_model_corrects_a_distorted_frame(marker_map, maps) -> None:
    uncorrected = _errors(marker_map, maps, None)
    corrected = _errors(marker_map, maps, TRUE_LENS)

    assert max(corrected) < CORRECTED_BOUND_MM
    for with_lens, without in zip(corrected, uncorrected, strict=True):
        assert with_lens < without / 2


def test_no_lens_is_the_unchanged_path(marker_map, maps) -> None:
    rvec, tvec = POSES[0]
    frame = render(
        _canvas(marker_map), plane_homography(rvec, tvec) @ _canvas_to_plane(), maps
    )
    pipeline = AimPipeline(marker_map, FakeCursorBackend())
    assert pipeline.process_frame(frame, debug=True) == pipeline.process_frame(
        frame, debug=True, lens=None
    )


def test_debug_geometry_stays_in_raw_pixels(marker_map, maps) -> None:
    rvec, tvec = POSES[0]
    frame = render(
        _canvas(marker_map), plane_homography(rvec, tvec) @ _canvas_to_plane(), maps
    )
    pipeline = AimPipeline(marker_map, FakeCursorBackend())
    plain = pipeline.process_frame(frame, debug=True)
    corrected = pipeline.process_frame(frame, debug=True, lens=TRUE_LENS)

    # Corners are reported as detected, whatever the lens.
    assert corrected.debug.markers == plain.debug.markers
    # The emitted cursor, carried back through the homography and the
    # lens, lands under the reticle at the frame centre.
    assert not corrected.clamped
    assert corrected.debug.cursor_px == pytest.approx(
        (IMAGE_SIZE[0] / 2, IMAGE_SIZE[1] / 2), abs=0.05
    )


def test_a_zero_is_measured_from_the_undistorted_centre(marker_map, maps) -> None:
    rvec, tvec = POSES[0]
    frame = render(
        _canvas(marker_map), plane_homography(rvec, tvec) @ _canvas_to_plane(), maps
    )
    pipeline = AimPipeline(marker_map, FakeCursorBackend())
    plain = pipeline.process_frame(frame, lens=TRUE_LENS)
    zeroed = pipeline.process_frame(frame, lens=TRUE_LENS, zero=Zero())

    # A zero with no correction aims exactly where the lens-corrected
    # solve does: both measure from the centre undistorted, not the raw
    # centre pixel, which here is ~2mm away on the screen.
    assert zeroed.aim_point_mm == pytest.approx(plain.aim_point_mm, abs=1e-6)
