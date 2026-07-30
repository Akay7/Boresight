import numpy as np
import pytest

from boresight.solve import InsufficientCorrespondencesError, solve

IMAGE_SIZE = (1920.0, 1080.0)

# A modest, well-conditioned ground-truth homography (screen-plane mm ->
# image-plane px): a plausible camera-like transform, not an arbitrary
# matrix, so the synthetic correspondences it produces stay well-behaved.
GROUND_TRUTH_HOMOGRAPHY = np.array(
    [
        [1.6, 0.05, 200.0],
        [-0.02, 1.55, 120.0],
        [0.0003, 0.0002, 1.0],
    ],
    dtype=np.float64,
)

# The 8-marker layout (4 corners + 4 edge midpoints) from README's Marker
# system section, in screen-plane mm.
SCREEN_MARKER_CORNERS_MM = [
    (-60.0, -60.0),
    (610.0, -60.0),
    (610.0, 626.0),
    (-60.0, 626.0),
    (275.0, -60.0),
    (610.0, 283.0),
    (275.0, 626.0),
    (-60.0, 283.0),
]


def _apply_homography(
    homography: np.ndarray, points: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Project points through a homography via plain numpy, independent of
    solve.py's own cv2 calls."""
    pts = np.array(points, dtype=np.float64)
    homogeneous = np.hstack([pts, np.ones((len(pts), 1))])
    projected = homogeneous @ homography.T
    projected /= projected[:, 2:3]
    return [(float(x), float(y)) for x, y in projected[:, :2]]


def test_recovers_known_aim_point_from_synthetic_correspondences():
    image_points = _apply_homography(GROUND_TRUTH_HOMOGRAPHY, SCREEN_MARKER_CORNERS_MM)
    correspondences = list(zip(SCREEN_MARKER_CORNERS_MM, image_points, strict=True))

    result = solve(correspondences, IMAGE_SIZE)

    true_inverse = np.linalg.inv(GROUND_TRUTH_HOMOGRAPHY)
    image_centre = [(IMAGE_SIZE[0] / 2.0, IMAGE_SIZE[1] / 2.0)]
    expected_aim_point = _apply_homography(true_inverse, image_centre)[0]

    # Noise-free synthetic correspondences: findHomography's least-squares
    # refit over inliers should recover the ground truth to within
    # floating-point precision, not just a loose visual tolerance.
    assert result.aim_point_mm == pytest.approx(expected_aim_point, abs=1e-2)


def test_insufficient_correspondences_raises_before_calling_findhomography():
    image_points = _apply_homography(
        GROUND_TRUTH_HOMOGRAPHY, SCREEN_MARKER_CORNERS_MM[:3]
    )
    correspondences = list(zip(SCREEN_MARKER_CORNERS_MM[:3], image_points, strict=True))

    with pytest.raises(InsufficientCorrespondencesError):
        solve(correspondences, IMAGE_SIZE)
