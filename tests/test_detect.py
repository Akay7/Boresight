"""detect.py on its own: corner accuracy, and the detector's lifetime.

The solve-level decks (test_solve_*.py) measure aim error, which mixes
corner error with the homography fit. This checks the corners directly
against the ground-truth warp of the checked-in synthetic photo, so a
lost or mistuned sub-pixel refinement shows up here as itself.

See tests/measure_detection.py for the before/after figures across all
fixtures.
"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from boresight.detect import detect_markers, thread_detector

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PHOTO_PATH = FIXTURES_DIR / "synthetic_photo.png"
PHOTO_METADATA_PATH = FIXTURES_DIR / "synthetic_photo.json"
VIDEO_DIR = FIXTURES_DIR / "esp32cam_video"

# Observed with refinement: mean 0.29px, worst 0.42px. Without it: mean
# 0.75px, worst 1.88px. 0.8px is 2x the refined worst case and well
# under the unrefined one.
MAX_CORNER_ERROR_PX = 0.8


def _marker_corners_mm(
    top_left: tuple[float, float], size: float
) -> list[tuple[float, float]]:
    x, y = top_left
    return [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]


def test_corners_are_refined_to_sub_pixel_accuracy():
    metadata = json.loads(PHOTO_METADATA_PATH.read_text())
    layout_mm = {int(k): tuple(v) for k, v in metadata["marker_layout_mm"].items()}
    homography = np.array(metadata["ground_truth_homography"])
    image = cv2.imread(str(PHOTO_PATH), cv2.IMREAD_GRAYSCALE)
    assert image is not None, f"fixture image not found at {PHOTO_PATH}"

    detected = detect_markers(image)
    assert len(detected) == len(layout_mm)

    for marker in detected:
        # 1 canvas px == 1 mm and pixel centres sit on integer
        # coordinates, so a marker's outer corner is half a pixel before
        # its first pixel.
        corners_mm = np.array(
            _marker_corners_mm(layout_mm[marker.marker_id], metadata["marker_size_mm"])
        )
        truth = cv2.perspectiveTransform(
            (corners_mm - 0.5).reshape(-1, 1, 2), homography
        )[:, 0, :]
        errors = np.linalg.norm(marker.corners - truth, axis=1)
        assert errors.max() < MAX_CORNER_ERROR_PX, (
            f"marker {marker.marker_id}: corner {int(errors.argmax())} is "
            f"{errors.max():.2f}px from ground truth"
        )


def test_a_thread_reuses_its_detector():
    assert thread_detector() is thread_detector()


def test_each_thread_gets_its_own_detector():
    detectors = []

    def record() -> None:
        detectors.append(thread_detector())

    threads = [threading.Thread(target=record) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len({id(detector) for detector in detectors + [thread_detector()]}) == 4


def test_concurrent_detection_matches_sequential():
    """Several sessions' frames in detection at once, as the server's
    executor runs them, give exactly what one thread would."""
    frames = [
        cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        for path in sorted(VIDEO_DIR.glob("frame_*.jpg"))
    ]
    assert frames

    def summarize(frame: np.ndarray) -> list[tuple[int, list[float]]]:
        return sorted(
            (marker.marker_id, marker.corners.ravel().tolist())
            for marker in detect_markers(frame)
        )

    sequential = [summarize(frame) for frame in frames]
    with ThreadPoolExecutor(max_workers=4) as executor:
        concurrent = list(executor.map(summarize, frames * 4))

    assert concurrent == sequential * 4
