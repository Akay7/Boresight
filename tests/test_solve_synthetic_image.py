"""Stage 2: solve.py exercised through real detection on a synthetic
image. Markers are rendered into a blank canvas (1 canvas px == 1 mm on
the screen plane) and warped by a known homography to simulate a camera
view -- no camera, no real capture, but real detect.py/cv2.aruco corner
extraction feeds solve.py rather than hand-built points.
"""

import cv2
import numpy as np
import pytest

from boresight.detect import detect_markers
from boresight.solve import solve

IMAGE_SIZE = (1920.0, 1080.0)
CANVAS_SIZE = (800, 800)
MARKER_SIZE_MM = 80.0

# Top-left corner of each marker's square, in screen-plane mm (1 mm == 1
# canvas px). Shifted to stay non-negative so it can be drawn directly
# onto a canvas without a separate translation to track.
MARKER_LAYOUT_MM = {
    0: (0.0, 0.0),
    1: (620.0, 0.0),
    2: (620.0, 620.0),
    3: (0.0, 620.0),
    4: (310.0, 0.0),
    5: (620.0, 310.0),
    6: (310.0, 620.0),
    7: (0.0, 310.0),
}

# Screen-plane mm -> synthetic image px. Modest scale/translation/skew,
# kept small enough that all markers land inside CANVAS_SIZE and their
# warped positions land inside IMAGE_SIZE.
GROUND_TRUTH_HOMOGRAPHY = np.array(
    [
        [1.2, 0.02, 150.0],
        [-0.01, 1.15, 100.0],
        [0.0002, 0.0001, 1.0],
    ],
    dtype=np.float64,
)


def _apply_homography(
    homography: np.ndarray, points: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    pts = np.array(points, dtype=np.float64)
    homogeneous = np.hstack([pts, np.ones((len(pts), 1))])
    projected = homogeneous @ homography.T
    projected /= projected[:, 2:3]
    return [(float(x), float(y)) for x, y in projected[:, :2]]


def _marker_corners_mm(
    top_left: tuple[float, float], size: float
) -> list[tuple[float, float]]:
    """Clockwise from top-left, matching cv2.aruco's detected corner order."""
    x, y = top_left
    return [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]


def _render_synthetic_image() -> np.ndarray:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    canvas = np.full(CANVAS_SIZE[::-1], 255, dtype=np.uint8)

    for marker_id, (x, y) in MARKER_LAYOUT_MM.items():
        marker_img = cv2.aruco.generateImageMarker(
            dictionary, marker_id, int(MARKER_SIZE_MM)
        )
        x, y = int(x), int(y)
        canvas[y : y + marker_img.shape[0], x : x + marker_img.shape[1]] = marker_img

    return cv2.warpPerspective(
        canvas,
        GROUND_TRUTH_HOMOGRAPHY,
        (int(IMAGE_SIZE[0]), int(IMAGE_SIZE[1])),
        borderValue=255,
    )


def test_detector_output_round_trips_through_solver():
    image = _render_synthetic_image()

    detected = detect_markers(image)
    assert len(detected) == len(MARKER_LAYOUT_MM), (
        f"expected all {len(MARKER_LAYOUT_MM)} synthetic markers to be "
        f"detected, got {len(detected)}"
    )

    correspondences = []
    for marker in detected:
        known_corners_mm = _marker_corners_mm(
            MARKER_LAYOUT_MM[marker.marker_id], MARKER_SIZE_MM
        )
        for screen_point, image_point in zip(
            known_corners_mm, marker.corners, strict=True
        ):
            correspondences.append(
                (screen_point, (float(image_point[0]), float(image_point[1])))
            )

    result = solve(correspondences, IMAGE_SIZE)

    true_inverse = np.linalg.inv(GROUND_TRUTH_HOMOGRAPHY)
    image_centre = [(IMAGE_SIZE[0] / 2.0, IMAGE_SIZE[1] / 2.0)]
    expected_aim_point = _apply_homography(true_inverse, image_centre)[0]

    # Looser than stage 1's tolerance: rendering, warpPerspective
    # interpolation, and the detector's own corner localization add real
    # numerical error beyond pure homography math (observed ~0.6mm here,
    # max per-corner reprojection error ~1.0px) -- 1.5mm leaves margin
    # without masking a real regression.
    assert result.aim_point_mm == pytest.approx(expected_aim_point, abs=1.5)
