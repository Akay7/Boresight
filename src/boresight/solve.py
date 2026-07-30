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

    return SolveResult(
        aim_point_mm=(float(aim_point[0]), float(aim_point[1])),
        homography=homography,
        reprojection_errors_px=reprojection_errors.tolist(),
    )
