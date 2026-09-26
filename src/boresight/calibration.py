"""Lens calibration from a ChArUco board seen in a session's own frames.

The board is a chessboard with an ArUco marker in each white square, so
every inner corner is identified even when only part of the board is in
view. That is what lets a handheld camera sweep it past the frame edges,
where the distortion is. The views come from the live stream rather
than from photos taken some other way, so they have the resolution,
processing and JPEG path the solver sees (see the `add-lens-calibration`
design, decision 1).

The board uses `DICT_5X5_100`, not the aim markers' `DICT_4X4_50`, so a
board in view never becomes aim correspondences.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np

from boresight.lens import LensModel

BOARD_DICTIONARY = "DICT_5X5_100"
BOARD_SQUARES = (7, 5)

# The board's pixel pattern is OpenCV's own `generateImage`, at sizes
# where every edge falls on a whole pixel: a 5x5 marker plus border is
# 7 cells, 8px each, inset 8px in a 72px square. The SVG is built from
# these pixels, so it is whatever the detector expects by construction.
SQUARE_PX = 72
MARKER_PX = 56

# Enough views to constrain k1, k2, p1, p2 and the intrinsics with room
# to spare; see Open Questions in the design for tuning on hardware.
VIEWS_NEEDED = 20

# A view must show at least this share of the board's inner corners.
MIN_CORNER_FRACTION = 0.5

# A new view must have moved this share of the image width (mean over
# the corners it shares with each kept view), or share fewer than half
# its corners with it. Keeps a board held still from filling every view.
MIN_VIEW_SHIFT = 0.05

# Above this RMS the views were blurred or the board was not flat, and
# the model would make aim worse than no model.
MAX_RMS_PX = 1.5

# k3 fixed at zero: with it free, a synthetic fit reproduced the same
# RMS with a strongly correlated k2/k3 pair that extrapolates badly
# past the outermost views (design, decision 3).
CALIBRATION_FLAGS = cv2.CALIB_FIX_K3


def board() -> cv2.aruco.CharucoBoard:
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, BOARD_DICTIONARY))
    return cv2.aruco.CharucoBoard(
        BOARD_SQUARES, float(SQUARE_PX), float(MARKER_PX), dictionary
    )


def board_image() -> np.ndarray:
    """The board, one pixel per pixel of its pattern, no margin."""
    columns, rows = BOARD_SQUARES
    return board().generateImage(
        (columns * SQUARE_PX, rows * SQUARE_PX), marginSize=0, borderBits=1
    )


def inner_corner_count() -> int:
    columns, rows = BOARD_SQUARES
    return (columns - 1) * (rows - 1)


def board_svg(width_mm: float) -> str:
    """The board as vector SVG, `width_mm` wide.

    One `<rect>` per horizontal run of black pixels in `board_image()`,
    inside a white quiet zone one square wide that the detector needs
    around the outer squares.
    """
    if not width_mm > 0:
        raise ValueError("width_mm must be positive")
    image = board_image()
    height, width = image.shape
    rects = []
    for row in range(height):
        black = np.flatnonzero(image[row] == 0)
        if black.size == 0:
            continue
        # Split into runs of consecutive columns.
        breaks = np.flatnonzero(np.diff(black) != 1) + 1
        for run in np.split(black, breaks):
            x = int(run[0]) + SQUARE_PX
            rects.append(
                f'<rect x="{x}" y="{row + SQUARE_PX}" width="{run.size}" height="1"/>'
            )
    total_w, total_h = width + 2 * SQUARE_PX, height + 2 * SQUARE_PX
    height_mm = width_mm * total_h / total_w
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {total_w} {total_h}" '
        f'width="{width_mm:g}mm" height="{height_mm:g}mm" '
        f'shape-rendering="crispEdges">'
        f'<rect x="0" y="0" width="{total_w}" height="{total_h}" fill="white"/>'
        f'<g fill="black">{"".join(rects)}</g>'
        "</svg>"
    )


@dataclass(frozen=True)
class View:
    """One kept frame's board corners, by corner id."""

    ids: np.ndarray
    corners: np.ndarray

    def shift_from(self, other: View) -> float | None:
        """Mean corner displacement over shared ids; None if too few shared."""
        shared, mine, theirs = np.intersect1d(
            self.ids, other.ids, assume_unique=True, return_indices=True
        )
        if len(shared) < len(self.ids) / 2:
            return None
        return float(
            np.linalg.norm(self.corners[mine] - other.corners[theirs], axis=1).mean()
        )


class CalibrationError(ValueError):
    """Too few views, or OpenCV could not fit them."""


def detect_view(detector: cv2.aruco.CharucoDetector, image: np.ndarray) -> View | None:
    """The board's inner corners in `image`, if enough of it is visible."""
    corners, ids, _marker_corners, _marker_ids = detector.detectBoard(image)
    if ids is None or len(ids) < MIN_CORNER_FRACTION * inner_corner_count():
        return None
    if detector.getBoard().checkCharucoCornersCollinear(ids):
        return None
    return View(ids=ids.ravel().astype(np.int32), corners=corners.reshape(-1, 2))


def calibrate(views: list[View], image_size: tuple[int, int]) -> LensModel:
    """Camera matrix and distortion from kept views; RMS in `rms_px`."""
    if len(views) < 4:
        raise CalibrationError(f"need at least 4 views, got {len(views)}")
    charuco = board()
    object_points, image_points = [], []
    for view in views:
        objects, images = charuco.matchImagePoints(
            view.corners.reshape(-1, 1, 2).astype(np.float32),
            view.ids.reshape(-1, 1),
        )
        object_points.append(objects)
        image_points.append(images)
    try:
        rms, matrix, coeffs, _rvecs, _tvecs = cv2.calibrateCamera(
            object_points,
            image_points,
            image_size,
            None,
            None,
            flags=CALIBRATION_FLAGS,
        )
    except cv2.error as error:
        raise CalibrationError(f"calibration failed: {error}") from error
    return LensModel(
        camera_matrix=matrix,
        dist_coeffs=coeffs.ravel(),
        image_size=(int(image_size[0]), int(image_size[1])),
        rms_px=float(rms),
        views=len(views),
    )


class CalibrationCapture:
    """One session's calibration: collect views, then fit and store.

    `offer` runs on the session's executor thread, one frame at a time;
    `status` and `cancel` run on the event loop. A lock covers the few
    fields both touch. The fit itself runs inside the `offer` that
    completes capture: ~15ms once, for one session's one frame.

    `on_result(key, lens)` is called with an accepted model, which is
    how it reaches the store without this module knowing about one.
    """

    def __init__(
        self,
        on_result: Callable[[str, LensModel], None],
        views_needed: int = VIEWS_NEEDED,
        max_rms_px: float = MAX_RMS_PX,
    ) -> None:
        self._on_result = on_result
        self._views_needed = views_needed
        self._max_rms_px = max_rms_px
        self._detector = cv2.aruco.CharucoDetector(board())
        self._lock = threading.Lock()
        self._views: list[View] = []
        self._size: tuple[int, int] | None = None
        self.state = "capturing"
        self.rms_px: float | None = None
        self.detail: str | None = None
        self.key: str | None = None

    @property
    def active(self) -> bool:
        return self.state == "capturing"

    def cancel(self) -> None:
        with self._lock:
            if self.active:
                self.state = "cancelled"
                self._views = []

    def offer(self, gray: np.ndarray, key: str) -> None:
        """Consider one frame; `key` is the session's lens key for it."""
        if not self.active:
            return
        height, width = gray.shape[:2]
        view = detect_view(self._detector, gray)
        with self._lock:
            if not self.active:
                return
            if self._size != (width, height) or self.key != key:
                # A resolution (or identity) change mid-capture: the views
                # so far belong to another camera model.
                self._size = (width, height)
                self.key = key
                self._views = []
            if view is None or not self._is_new(view, width):
                return
            self._views.append(view)
            if len(self._views) < self._views_needed:
                return
            views = list(self._views)
        self._finish(views, (width, height), key)

    def _is_new(self, view: View, width: int) -> bool:
        for kept in self._views:
            shift = view.shift_from(kept)
            if shift is not None and shift < MIN_VIEW_SHIFT * width:
                return False
        return True

    def _finish(self, views: list[View], size: tuple[int, int], key: str) -> None:
        try:
            lens = calibrate(views, size)
        except CalibrationError as error:
            with self._lock:
                self.state, self.detail = "failed", str(error)
            return
        with self._lock:
            self.rms_px = lens.rms_px
            if lens.rms_px > self._max_rms_px:
                self.state = "failed"
                self.detail = (
                    f"reprojection error {lens.rms_px:.2f}px is above "
                    f"{self._max_rms_px:g}px; hold the board flat and still"
                )
                return
        self._on_result(key, lens)
        with self._lock:
            self.state = "done"

    def status(self) -> dict:
        with self._lock:
            return {
                "state": self.state,
                "views": len(self._views),
                "views_needed": self._views_needed,
                "rms_px": None if self.rms_px is None else round(self.rms_px, 3),
                "detail": self.detail,
            }
