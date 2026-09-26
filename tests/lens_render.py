"""Rendering a flat texture through a synthetic camera with lens distortion.

A pinhole view of a plane is a homography, `K [r1 r2 t]`, so the ideal
image is one `warpPerspective`. Distortion is then applied the way a
lens does: each output (distorted) pixel samples the ideal image at its
own undistorted position, computed once per camera with
`undistortPoints`. Everything is exact up to interpolation, and the
ground truth (where any plane point lands, and what the frame centre
looks at) comes from the same K, R, t and D.
"""

from __future__ import annotations

import cv2
import numpy as np

# A phone-like 640x480 camera with strong barrel distortion: at the
# frame corners this moves points by ~25px, well past anything the
# homography could absorb.
IMAGE_SIZE = (640, 480)
CAMERA_MATRIX = np.array([[500.0, 0.0, 322.0], [0.0, 500.0, 236.0], [0.0, 0.0, 1.0]])
DIST_COEFFS = np.array([-0.30, 0.10, 0.001, -0.001, 0.0])


def plane_homography(
    rvec: np.ndarray, tvec: np.ndarray, camera_matrix: np.ndarray = CAMERA_MATRIX
) -> np.ndarray:
    """Plane (z=0, same units as tvec) -> ideal image pixels."""
    rotation, _ = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64))
    return camera_matrix @ np.column_stack([rotation[:, 0], rotation[:, 1], tvec])


def distortion_maps(
    size: tuple[int, int] = IMAGE_SIZE,
    camera_matrix: np.ndarray = CAMERA_MATRIX,
    dist_coeffs: np.ndarray = DIST_COEFFS,
) -> tuple[np.ndarray, np.ndarray]:
    width, height = size
    xs, ys = np.meshgrid(
        np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32)
    )
    pixels = np.stack([xs.ravel(), ys.ravel()], axis=1).reshape(-1, 1, 2)
    ideal = cv2.undistortPoints(
        pixels,
        camera_matrix,
        dist_coeffs,
        P=camera_matrix,
        criteria=(cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 40, 1e-7),
    ).reshape(height, width, 2)
    return ideal[..., 0].astype(np.float32), ideal[..., 1].astype(np.float32)


def render(
    texture: np.ndarray,
    texture_to_ideal: np.ndarray,
    maps: tuple[np.ndarray, np.ndarray] | None,
    size: tuple[int, int] = IMAGE_SIZE,
    background: int = 128,
) -> np.ndarray:
    """`texture` placed by a homography into the ideal image, then distorted.

    `maps` None renders the ideal (undistorted) image.
    """
    ideal = cv2.warpPerspective(
        texture,
        texture_to_ideal,
        size,
        flags=cv2.INTER_AREA,
        borderValue=background,
    )
    if maps is None:
        return ideal
    return cv2.remap(ideal, maps[0], maps[1], cv2.INTER_LINEAR, borderValue=background)
