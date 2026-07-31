"""Unit tests for solve.py's conditioning signal. Pure geometry.

The signal exists because accuracy is governed by where the aim point
sits relative to the fitted correspondences, not by how many markers
were seen -- and because reprojection error, the only other quality
number solve() returns, is anti-correlated with accuracy in exactly the
case that matters (see test_reprojection_error_cannot_replace_this).
"""

import numpy as np
import pytest

from boresight.solve import solve

IMAGE_SIZE = (1920.0, 1080.0)

# Screen mm -> image px. Chosen so the image centre maps to screen
# (400, 400), comfortably inside the well-spread layout below.
GROUND_TRUTH_HOMOGRAPHY = np.array(
    [
        [1.2, 0.0, 480.0],
        [0.0, 1.2, 60.0],
        [0.0, 0.0, 1.0],
    ],
    dtype=np.float64,
)

# Markers spread around the aim point.
WELL_SPREAD_MM = [
    (0.0, 0.0),
    (800.0, 0.0),
    (800.0, 800.0),
    (0.0, 800.0),
]

# A single 80mm marker's four corners, far from the aim point: the
# sparse-visibility case, where the aim point is extrapolated well
# outside the fitted region.
CLUSTERED_MM = [
    (0.0, 0.0),
    (80.0, 0.0),
    (80.0, 80.0),
    (0.0, 80.0),
]


def _correspondences(screen_points):
    pts = np.array(screen_points, dtype=np.float64)
    homogeneous = np.hstack([pts, np.ones((len(pts), 1))])
    projected = homogeneous @ GROUND_TRUTH_HOMOGRAPHY.T
    projected /= projected[:, 2:3]
    return [
        (tuple(screen), (float(x), float(y)))
        for screen, (x, y) in zip(screen_points, projected[:, :2], strict=True)
    ]


def test_aim_point_inside_the_marker_footprint_is_reported_as_interpolated():
    result = solve(_correspondences(WELL_SPREAD_MM), IMAGE_SIZE)

    assert result.aim_point_inside_hull
    # Positive distance == margin to the hull boundary, so an interior
    # point reports how much evidence surrounds it.
    assert result.aim_point_hull_distance_mm > 0.0
    assert result.correspondence_extent_mm == pytest.approx((800.0, 800.0))


def test_aim_point_beyond_the_marker_footprint_is_reported_as_extrapolated():
    result = solve(_correspondences(CLUSTERED_MM), IMAGE_SIZE)

    assert not result.aim_point_inside_hull
    # Negative == outside, and the magnitude says how far past the
    # evidence the answer lies: here hundreds of mm beyond an 80mm
    # marker.
    assert result.aim_point_hull_distance_mm < 0.0
    assert abs(result.aim_point_hull_distance_mm) > 100.0
    assert result.correspondence_extent_mm == pytest.approx((80.0, 80.0))


def test_conditioning_does_not_change_the_aim_point():
    """The fields are additional data, never an input to the solution."""
    spread = solve(_correspondences(WELL_SPREAD_MM), IMAGE_SIZE)
    clustered = solve(_correspondences(CLUSTERED_MM), IMAGE_SIZE)

    # Both fit the same ground-truth homography, so both must recover
    # the same aim point exactly -- the conditioning differs, the
    # answer does not. Noise-free input, so this is an exact check
    # rather than a tolerance.
    assert spread.aim_point_mm == pytest.approx(clustered.aim_point_mm, abs=1e-6)


def test_reprojection_error_cannot_replace_this():
    """Why the hull signal exists at all.

    Four points fix a homography exactly, so a single marker fits with
    ~zero reprojection error while its aim point is the least
    trustworthy. Any consumer using reprojection error as a validity
    check would rank this solve above a well-spread one.
    """
    clustered = solve(_correspondences(CLUSTERED_MM), IMAGE_SIZE)

    assert max(clustered.reprojection_errors_px) == pytest.approx(0.0, abs=1e-6)
    assert not clustered.aim_point_inside_hull
