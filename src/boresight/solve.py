"""Homography solving: marker correspondences -> screen-space aim point.

Takes marker correspondences -- each a known screen-plane position (mm,
from markers.toml) paired with a detected image-plane position (px) --
and solves for where the image centre lands in screen space. Pure
geometry: no file I/O, no detector, no camera. Callers assemble
correspondences from wherever they come from, whether real config +
detection or a synthetic fixture.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np

MIN_CORRESPONDENCES = 4

Point = tuple[float, float]
Correspondence = tuple[Point, Point]


class InsufficientCorrespondencesError(ValueError):
    """Raised when fewer than MIN_CORRESPONDENCES correspondences are given."""


@dataclass
class SolveResult:
    aim_point_mm: Point
    homography: np.ndarray
    reprojection_errors_px: list[float]

    # How much evidence the aim point actually rests on. The homography
    # is fitted from the marker corners; pushing the image centre
    # through it is interpolation only while the aim point lies within
    # those corners, and extrapolation otherwise -- where small corner
    # errors are amplified without bound. Measured on a rendered
    # sequence: with the whole layout visible the aim point sits inside
    # the hull and lands within ~1.5mm; from a single 80mm marker it is
    # hundreds of mm outside and has been observed 2m off, on a 1220mm
    # panel.
    #
    # Do NOT substitute reprojection_errors_px for this. A single
    # marker gives four points and eight degrees of freedom, so the fit
    # is exact and its reprojection error is ~0 precisely when the aim
    # point is worst -- it is anti-correlated with accuracy here.
    aim_point_inside_hull: bool = True
    aim_point_hull_distance_mm: float = 0.0
    correspondence_extent_mm: Point = (0.0, 0.0)


def _conditioning(screen_pts: np.ndarray, aim_point: np.ndarray):
    """Where the aim point sits relative to the fitted correspondences.

    Returns (inside, signed distance in mm, extent). The distance uses
    cv2.pointPolygonTest's convention: positive inside the hull,
    negative outside, so it reads as "margin" when good and "how far
    past the evidence" when not.
    """
    hull = cv2.convexHull(screen_pts.astype(np.float32))
    distance = float(
        cv2.pointPolygonTest(hull, (float(aim_point[0]), float(aim_point[1])), True)
    )
    extent = screen_pts.max(axis=0) - screen_pts.min(axis=0)
    return distance >= 0.0, distance, (float(extent[0]), float(extent[1]))


def solve(correspondences: Sequence[Correspondence], image_size: Point) -> SolveResult:
    if len(correspondences) < MIN_CORRESPONDENCES:
        raise InsufficientCorrespondencesError(
            f"homography requires at least {MIN_CORRESPONDENCES} "
            f"correspondences, got {len(correspondences)}"
        )

    screen_pts = np.array([c[0] for c in correspondences], dtype=np.float64)
    image_pts = np.array([c[1] for c in correspondences], dtype=np.float64)

    homography, _ = cv2.findHomography(screen_pts, image_pts, cv2.RANSAC)
    if homography is None:
        raise ValueError(
            "could not compute a homography from the given correspondences"
        )

    homography_inv = np.linalg.inv(homography)

    width, height = image_size
    image_centre = np.array([[[width / 2.0, height / 2.0]]], dtype=np.float64)
    aim_point = cv2.perspectiveTransform(image_centre, homography_inv)[0, 0]

    projected = cv2.perspectiveTransform(screen_pts.reshape(-1, 1, 2), homography)
    reprojection_errors = np.linalg.norm(projected[:, 0, :] - image_pts, axis=1)

    inside_hull, hull_distance, extent = _conditioning(screen_pts, aim_point)

    return SolveResult(
        aim_point_mm=(float(aim_point[0]), float(aim_point[1])),
        homography=homography,
        reprojection_errors_px=reprojection_errors.tolist(),
        aim_point_inside_hull=inside_hull,
        aim_point_hull_distance_mm=hull_distance,
        correspondence_extent_mm=extent,
    )
