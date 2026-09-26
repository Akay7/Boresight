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

from boresight.calibration import SQUARE_PX, board_image

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


def padded_board() -> np.ndarray:
    image = board_image()
    return cv2.copyMakeBorder(
        image,
        SQUARE_PX,
        SQUARE_PX,
        SQUARE_PX,
        SQUARE_PX,
        cv2.BORDER_CONSTANT,
        value=255,
    )


def board_view(rvec, tvec, maps) -> np.ndarray:
    """The padded board, centred on the plane origin, 1 px == 1 plane unit."""
    texture = padded_board()
    height, width = texture.shape
    centre = np.array([[1.0, 0, -width / 2], [0, 1.0, -height / 2], [0, 0, 1.0]])
    return render(texture, plane_homography(rvec, tvec) @ centre, maps)


def random_board_views(maps, count: int, seed: int = 1) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    frames = []
    for _ in range(count):
        rvec = rng.uniform(-0.5, 0.5, 3) * np.array([1.0, 1.0, 0.3])
        # Wide enough to put board corners near the frame edges: a fit is
        # only good where its views reached, so a test that stays central
        # cannot tell a right model from one that is wrong at the edges.
        tvec = np.array(
            [rng.uniform(-260, 260), rng.uniform(-195, 195), rng.uniform(450, 750)]
        )
        frames.append(board_view(rvec, tvec, maps))
    return frames
