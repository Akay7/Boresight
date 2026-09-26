"""ChArUco board and calibration, on views rendered through a known lens."""

import re

import cv2
import numpy as np
import pytest
from lens_render import (
    CAMERA_MATRIX,
    DIST_COEFFS,
    IMAGE_SIZE,
    board_view,
    distortion_maps,
    padded_board,
    random_board_views,
)

from boresight.calibration import (
    CalibrationCapture,
    board,
    board_svg,
    calibrate,
    detect_view,
    inner_corner_count,
)
from boresight.detect import detect_markers
from boresight.lens import LensModel


@pytest.fixture(scope="module")
def maps():
    return distortion_maps()


# --- The board ----------------------------------------------------------


def test_board_raster_is_fully_detected() -> None:
    detector = cv2.aruco.CharucoDetector(board())
    view = detect_view(detector, padded_board())
    assert view is not None
    assert len(view.ids) == inner_corner_count()


def test_aim_detector_ignores_the_board() -> None:
    assert detect_markers(padded_board()) == []


def test_board_svg_reproduces_the_raster_exactly() -> None:
    svg = board_svg(250.0)
    padded = padded_board()
    rebuilt = np.full_like(padded, 255)
    for x, y, width in re.findall(
        r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="1"/>', svg
    ):
        rebuilt[int(y), int(x) : int(x) + int(width)] = 0
    assert np.array_equal(rebuilt, padded)


def test_board_svg_dimensions() -> None:
    height, width = padded_board().shape
    svg = board_svg(250.0)
    assert 'width="250mm"' in svg
    height_mm = float(re.search(r'height="([\d.]+)mm"', svg).group(1))
    assert height_mm == pytest.approx(250.0 * height / width, abs=1e-3)


@pytest.mark.parametrize("width", [0.0, -5.0])
def test_board_svg_rejects_non_positive_width(width: float) -> None:
    with pytest.raises(ValueError):
        board_svg(width)


# --- Calibration --------------------------------------------------------


def test_synthetic_distortion_is_recovered(maps) -> None:
    detector = cv2.aruco.CharucoDetector(board())
    views = [detect_view(detector, frame) for frame in random_board_views(maps, 30)]
    views = [view for view in views if view is not None]
    assert len(views) >= 25

    lens = calibrate(views, IMAGE_SIZE)
    assert lens.rms_px < 1.0
    assert lens.camera_matrix[0, 0] == pytest.approx(CAMERA_MATRIX[0, 0], rel=0.02)

    # Coefficients trade off against one another, so compare what the
    # models do: undistort a grid spanning the region the views covered
    # (~65-565 x 50-420 here) with both. Past it the fit extrapolates,
    # which is why the board page asks for views reaching the edges.
    truth = LensModel(CAMERA_MATRIX, DIST_COEFFS, IMAGE_SIZE)
    covered = np.concatenate([view.corners for view in views])
    low, high = covered.min(axis=0), covered.max(axis=0)
    xs, ys = np.meshgrid(
        np.linspace(low[0], high[0], 13), np.linspace(low[1], high[1], 9)
    )
    grid = np.stack([xs.ravel(), ys.ravel()], axis=1)
    disagreement = np.linalg.norm(
        lens.undistort_points(grid) - truth.undistort_points(grid), axis=1
    )
    assert disagreement.max() < 1.0


def _capture(**kwargs):
    stored = []
    capture = CalibrationCapture(lambda key, lens: stored.append((key, lens)), **kwargs)
    return capture, stored


def test_board_held_still_gives_one_view(maps) -> None:
    capture, _ = _capture()
    frame = board_view(np.zeros(3), np.array([0.0, 0.0, 700.0]), maps)
    for _ in range(5):
        capture.offer(frame, "k")
    assert capture.status()["views"] == 1

    moved = board_view(np.array([0.3, 0.0, 0.0]), np.array([60.0, 0.0, 700.0]), maps)
    capture.offer(moved, "k")
    assert capture.status()["views"] == 2


def test_frames_without_the_board_are_not_kept() -> None:
    capture, _ = _capture()
    capture.offer(np.full(IMAGE_SIZE[::-1], 128, np.uint8), "k")
    assert capture.status() == {
        "state": "capturing",
        "views": 0,
        "views_needed": 20,
        "rms_px": None,
        "detail": None,
    }


def test_a_resolution_change_restarts_capture(maps) -> None:
    capture, _ = _capture()
    capture.offer(board_view(np.zeros(3), np.array([0.0, 0.0, 700.0]), maps), "k")
    assert capture.status()["views"] == 1
    capture.offer(np.full((600, 800), 128, np.uint8), "k")
    assert capture.status()["views"] == 0


def test_capture_completes_and_stores(maps) -> None:
    capture, stored = _capture(views_needed=12)
    for frame in random_board_views(maps, 30, seed=3):
        capture.offer(frame, "phone||640x480")
        if not capture.active:
            break
    status = capture.status()
    assert status["state"] == "done"
    assert status["rms_px"] < 1.0
    assert [key for key, _ in stored] == ["phone||640x480"]


def test_a_poor_fit_is_not_stored(maps) -> None:
    capture, stored = _capture(views_needed=6, max_rms_px=1e-6)
    for frame in random_board_views(maps, 20, seed=4):
        capture.offer(frame, "k")
        if not capture.active:
            break
    status = capture.status()
    assert status["state"] == "failed"
    assert status["rms_px"] is not None
    assert stored == []


def test_cancel_stops_capture(maps) -> None:
    capture, _ = _capture()
    capture.cancel()
    capture.offer(board_view(np.zeros(3), np.array([0.0, 0.0, 700.0]), maps), "k")
    assert capture.status()["state"] == "cancelled"
    assert capture.status()["views"] == 0
