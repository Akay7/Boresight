"""The per-session fast path: `MarkerTracker` and its coarse pass.

What it must never do is lose a detection or move a corner, so most of
these compare it against `detect_markers` on the same frames. The
bounds come from tests/measure_detection_speed.py, which prints the
observed values.
"""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from boresight.detect import (
    COARSE_MIN_SIDE_PX,
    FULL_PASS_EVERY_FRAMES,
    DetectedMarker,
    MarkerTracker,
    detect_markers,
    detect_markers_coarse,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PHOTO_PATH = FIXTURES_DIR / "synthetic_photo.png"
PHOTO_METADATA_PATH = FIXTURES_DIR / "synthetic_photo.json"

# Observed: 0.041px on the phone fixture, 0.026px on the photo.
MAX_DEVIATION_FROM_FULL_PX = 0.1
# test_detect.py's ground-truth bound for the full pass.
MAX_CORNER_ERROR_PX = 0.8


def _frames(name: str) -> list[np.ndarray]:
    manifest = json.loads((FIXTURES_DIR / name / "manifest.json").read_text())
    return [
        cv2.imread(str(FIXTURES_DIR / name / entry["file"]), cv2.IMREAD_GRAYSCALE)
        for entry in manifest["frames"]
    ]


@pytest.fixture(scope="module")
def phone_frames() -> list[np.ndarray]:
    return _frames("synthetic_video")


@pytest.fixture(scope="module")
def photo() -> np.ndarray:
    image = cv2.imread(str(PHOTO_PATH), cv2.IMREAD_GRAYSCALE)
    assert image is not None, f"fixture image not found at {PHOTO_PATH}"
    return image


def _by_id(markers) -> dict[int, np.ndarray]:
    return {marker.marker_id: marker.corners for marker in markers}


def _summary(markers) -> list[tuple[int, list[float]]]:
    return sorted((m.marker_id, m.corners.ravel().tolist()) for m in markers)


def _hide(image: np.ndarray, marker: DetectedMarker, margin: int = 6) -> np.ndarray:
    """The frame with one marker painted out, quiet zone and all."""
    hidden = image.copy()
    x0, y0 = np.floor(marker.corners.min(axis=0)).astype(int) - margin
    x1, y1 = np.ceil(marker.corners.max(axis=0)).astype(int) + margin
    hidden[max(0, y0) : y1, max(0, x0) : x1] = 255
    return hidden


def _ground_truth_errors(markers) -> np.ndarray:
    metadata = json.loads(PHOTO_METADATA_PATH.read_text())
    layout_mm = {int(k): tuple(v) for k, v in metadata["marker_layout_mm"].items()}
    homography = np.array(metadata["ground_truth_homography"])
    size = metadata["marker_size_mm"]
    errors = []
    for marker in markers:
        x, y = layout_mm[marker.marker_id]
        # Pixel centres on integer coordinates: see test_detect.py.
        corners_mm = np.array(
            [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]
        )
        truth = cv2.perspectiveTransform(
            (corners_mm - 0.5).reshape(-1, 1, 2), homography
        )[:, 0, :]
        errors.extend(np.linalg.norm(marker.corners - truth, axis=1))
    return np.array(errors)


# --- The coarse pass ----------------------------------------------------


def test_coarse_corners_meet_the_ground_truth_bound(photo) -> None:
    coarse = detect_markers_coarse(photo)
    full = detect_markers(photo)

    assert {m.marker_id for m in coarse} == {m.marker_id for m in full}
    errors = _ground_truth_errors(coarse)
    assert errors.max() < MAX_CORNER_ERROR_PX
    # No worse on average than the full pass (0.289 vs 0.288px observed).
    assert errors.mean() < _ground_truth_errors(full).mean() + 0.05


def test_coarse_corners_are_in_full_resolution_pixels(photo) -> None:
    full = _by_id(detect_markers(photo))
    for marker in detect_markers_coarse(photo):
        deviation = np.linalg.norm(marker.corners - full[marker.marker_id], axis=1)
        assert deviation.max() < MAX_DEVIATION_FROM_FULL_PX


# --- The tracker --------------------------------------------------------


def test_tracking_the_phone_fixture_matches_the_full_pass(phone_frames) -> None:
    tracker = MarkerTracker()

    for index, frame in enumerate(phone_frames):
        full = _by_id(detect_markers(frame))
        tracked = _by_id(tracker(frame))
        assert tracked.keys() == full.keys(), f"frame {index}"
        for marker_id, corners in tracked.items():
            deviation = np.linalg.norm(corners - full[marker_id], axis=1).max()
            assert deviation < MAX_DEVIATION_FROM_FULL_PX, (
                f"frame {index} marker {marker_id}: {deviation:.3f}px"
            )

    # 18 of 20 observed: the first frame and the periodic full pass.
    assert tracker.coarse_passes >= 15


def test_markers_too_small_for_the_coarse_pass_stay_on_the_full_pass() -> None:
    """The ESP32-CAM fixture's ~25px markers: the coarse pass lost a third
    of them, so it must never be tried."""
    tracker = MarkerTracker()
    for frame in _frames("esp32cam_video"):
        assert _summary(tracker(frame)) == _summary(detect_markers(frame))
    assert tracker.coarse_passes == 0
    assert tracker.coarse_misses == 0


def test_a_lost_marker_is_searched_for_in_full_on_the_same_frame(
    phone_frames,
) -> None:
    frame = phone_frames[0]
    tracker = MarkerTracker()
    tracker(frame)
    hidden = _hide(frame, detect_markers(frame)[0])

    result = tracker(hidden)

    assert tracker.coarse_misses == 1
    assert _summary(result) == _summary(detect_markers(hidden))


def test_a_coarse_marker_too_small_to_trust_is_searched_for_in_full(
    phone_frames,
) -> None:
    frame = phone_frames[0]
    real = detect_markers(frame)
    tiny = DetectedMarker(
        marker_id=49,
        corners=np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.float32),
    )
    full_calls = []

    def full(image):
        full_calls.append(image)
        return detect_markers(image)

    tracker = MarkerTracker(full=full, coarse=lambda _image: [*real, tiny])
    tracker(frame)
    result = tracker(frame)

    assert len(full_calls) == 2
    assert 49 not in {marker.marker_id for marker in result}


def test_nothing_tracked_means_a_full_pass() -> None:
    blank = np.full((120, 160), 255, dtype=np.uint8)
    coarse_calls = []
    tracker = MarkerTracker(coarse=lambda image: coarse_calls.append(image) or [])

    for _ in range(3):
        assert tracker(blank) == []

    assert coarse_calls == []
    assert tracker.full_passes == 3


@pytest.mark.parametrize("coarse_sees_newcomers", [True, False])
def test_a_marker_that_appears_is_found_within_the_bound(
    phone_frames, coarse_sees_newcomers
) -> None:
    """Even a coarse pass that never finds a new marker -- one too small
    for it -- cannot hide it for longer than the periodic full pass."""
    frame = phone_frames[-1]
    newcomer = detect_markers(frame)[0]
    hidden = _hide(frame, newcomer)

    def blind_coarse(image):
        return [
            marker
            for marker in detect_markers_coarse(image)
            if marker.marker_id != newcomer.marker_id
        ]

    tracker = MarkerTracker(
        coarse=detect_markers_coarse if coarse_sees_newcomers else blind_coarse
    )
    for _ in range(7):
        assert newcomer.marker_id not in _by_id(tracker(hidden))

    seen = [
        newcomer.marker_id in _by_id(tracker(frame))
        for _ in range(FULL_PASS_EVERY_FRAMES)
    ]
    assert any(seen), f"not found within {FULL_PASS_EVERY_FRAMES} frames"
    if coarse_sees_newcomers:
        assert seen[0]


def test_interleaved_sessions_detect_as_if_alone(phone_frames, photo) -> None:
    photos = [photo] * len(phone_frames)
    alone_phone = [_summary(m) for m in map(MarkerTracker(), phone_frames)]
    alone_photo = [_summary(m) for m in map(MarkerTracker(), photos)]

    first, second = MarkerTracker(), MarkerTracker()
    interleaved_phone, interleaved_photo = [], []
    for phone_frame, photo_frame in zip(phone_frames, photos, strict=True):
        interleaved_phone.append(_summary(first(phone_frame)))
        interleaved_photo.append(_summary(second(photo_frame)))

    assert interleaved_phone == alone_phone
    assert interleaved_photo == alone_photo


def test_the_size_gate_sits_between_the_two_camera_fixtures(phone_frames) -> None:
    """The gate's reason for its value: under the phone fixture's
    smallest marker, above the ESP32-CAM's largest."""
    phone = min(
        min(np.linalg.norm(m.corners - np.roll(m.corners, 1, axis=0), axis=1))
        for frame in phone_frames
        for m in detect_markers(frame)
    )
    esp32 = max(
        max(np.linalg.norm(m.corners - np.roll(m.corners, 1, axis=0), axis=1))
        for frame in _frames("esp32cam_video")
        for m in detect_markers(frame)
    )
    assert esp32 < COARSE_MIN_SIDE_PX < phone


def test_a_coarse_pass_that_keeps_missing_is_rarely_tried(phone_frames) -> None:
    """A camera the coarse pass fails on costs at most one wasted coarse
    pass per backoff window, not one per frame."""
    frame = phone_frames[0]
    coarse_calls = []

    def always_misses(image):
        coarse_calls.append(image)
        return []

    tracker = MarkerTracker(coarse=always_misses)
    for _ in range(30):
        assert _summary(tracker(frame)) == _summary(detect_markers(frame))

    assert len(coarse_calls) <= 3
