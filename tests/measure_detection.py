"""Measures detect.py against every checked-in fixture with ground truth.

Compares the current detector with OpenCV's defaults (no corner
refinement, detector rebuilt on every call -- detect.py as it stood
before `improve-marker-detection`), on the numbers that decide whether
a detector change is an improvement:

- corner error, px: detected corners against the ground-truth
  homography (synthetic_photo only; the video manifests carry the aim
  point but not per-corner truth)
- aim error, mm: max and mean of solve()'s aim point against the
  manifest's (close_range: inside-hull frames only, as its test does)
- delta error, mm: worst frame-to-frame aim change against the
  ground-truth change -- the jitter figure
- markers found, summed over frames, and detection time per frame

Run manually when touching detection:

    uv run python tests/measure_detection.py

Not part of the test suite; the regression tests assert on bounds, this
prints the observed values the bounds were chosen from.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from boresight.detect import DICTIONARY, DetectedMarker, detect_markers
from boresight.solve import solve

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VIDEO_FIXTURES = ("synthetic_video", "esp32cam_video", "close_range")
TIMING_REPEATS = 10

Detector = Callable[[np.ndarray], list[DetectedMarker]]


def detect_markers_before(image: np.ndarray) -> list[DetectedMarker]:
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICTIONARY))
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
    corners, ids, _rejected = detector.detectMarkers(image)
    if ids is None:
        return []
    return [
        DetectedMarker(marker_id=int(marker_id), corners=marker_corners[0])
        for marker_corners, marker_id in zip(corners, ids, strict=True)
    ]


def _marker_corners_mm(
    top_left: tuple[float, float], size: float
) -> list[tuple[float, float]]:
    x, y = top_left
    return [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]


def _project(homography: np.ndarray, points) -> np.ndarray:
    array = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(array, homography)[:, 0, :]


def _solve(detected, layout_mm, marker_size_mm, image_size):
    correspondences = []
    for marker in detected:
        for screen_point, image_point in zip(
            _marker_corners_mm(layout_mm[marker.marker_id], marker_size_mm),
            marker.corners,
            strict=True,
        ):
            correspondences.append(
                (screen_point, (float(image_point[0]), float(image_point[1])))
            )
    return solve(correspondences, image_size)


def _ms_per_frame(detect: Detector, frames: list[np.ndarray]) -> float:
    detect(frames[0])  # a thread's first call builds its detector
    started = time.perf_counter()
    for _ in range(TIMING_REPEATS):
        for frame in frames:
            detect(frame)
    return (time.perf_counter() - started) * 1000.0 / TIMING_REPEATS / len(frames)


def measure_photo(detect: Detector) -> dict:
    metadata = json.loads((FIXTURES_DIR / "synthetic_photo.json").read_text())
    image = cv2.imread(str(FIXTURES_DIR / "synthetic_photo.png"), cv2.IMREAD_GRAYSCALE)
    layout_mm = {int(k): tuple(v) for k, v in metadata["marker_layout_mm"].items()}
    size_mm = metadata["marker_size_mm"]
    image_size = tuple(metadata["image_size"])
    homography = np.array(metadata["ground_truth_homography"])

    detected = detect(image)
    corner_errors = []
    for marker in detected:
        # The fixture is drawn at 1 canvas px == 1 mm, and a pixel's
        # centre sits at its integer coordinate, so a marker's outer
        # edge -- its corner -- is half a pixel before its first pixel.
        truth = _project(
            homography,
            np.array(_marker_corners_mm(layout_mm[marker.marker_id], size_mm)) - 0.5,
        )
        corner_errors.extend(np.linalg.norm(marker.corners - truth, axis=1))

    result = _solve(detected, layout_mm, size_mm, image_size)
    centre = [(image_size[0] / 2.0, image_size[1] / 2.0)]
    truth_aim = _project(np.linalg.inv(homography), centre)[0]
    return {
        "markers": len(detected),
        "corner_mean_px": float(np.mean(corner_errors)),
        "corner_max_px": float(np.max(corner_errors)),
        "aim_mm": float(np.linalg.norm(np.array(result.aim_point_mm) - truth_aim)),
        "ms_per_frame": _ms_per_frame(detect, [image]),
    }


def measure_video(detect: Detector, name: str) -> dict:
    directory = FIXTURES_DIR / name
    manifest = json.loads((directory / "manifest.json").read_text())
    layout_mm = {int(k): tuple(v) for k, v in manifest["marker_layout_mm"].items()}
    size_mm = manifest["marker_size_mm"]
    image_size = tuple(manifest["image_size"])
    frames = [
        cv2.cvtColor(cv2.imread(str(directory / entry["file"])), cv2.COLOR_BGR2GRAY)
        for entry in manifest["frames"]
    ]

    markers = 0
    errors = []
    recovered = []
    truth = []
    for entry, frame in zip(manifest["frames"], frames, strict=True):
        detected = detect(frame)
        markers += len(detected)
        if not detected:
            continue
        result = _solve(detected, layout_mm, size_mm, image_size)
        if name == "close_range" and not result.aim_point_inside_hull:
            continue
        recovered.append(result.aim_point_mm)
        truth.append(entry["aim_point_screen_mm"])
        errors.append(float(np.hypot(*(np.array(result.aim_point_mm) - truth[-1]))))

    measured = {
        "markers": markers,
        "aim_max_mm": max(errors),
        "aim_mean_mm": float(np.mean(errors)),
        "ms_per_frame": _ms_per_frame(detect, frames),
    }
    if name != "close_range":
        residuals = np.diff(np.array(recovered), axis=0) - np.diff(
            np.array(truth), axis=0
        )
        measured["delta_max_mm"] = float(np.linalg.norm(residuals, axis=1).max())
    return measured


def main() -> None:
    for label, detect in (("before", detect_markers_before), ("after", detect_markers)):
        print(f"== {label}")
        photo = measure_photo(detect)
        print(
            f"  synthetic_photo  markers {photo['markers']:3d}  "
            f"corner mean/max {photo['corner_mean_px']:.2f}/"
            f"{photo['corner_max_px']:.2f}px  aim {photo['aim_mm']:.2f}mm  "
            f"{photo['ms_per_frame']:.2f}ms/frame"
        )
        for name in VIDEO_FIXTURES:
            video = measure_video(detect, name)
            delta = video.get("delta_max_mm")
            print(
                f"  {name:16s} markers {video['markers']:3d}  "
                f"aim max/mean {video['aim_max_mm']:.2f}/{video['aim_mean_mm']:.2f}mm"
                + ("" if delta is None else f"  delta max {delta:.2f}mm")
                + f"  {video['ms_per_frame']:.2f}ms/frame"
            )


if __name__ == "__main__":
    main()
