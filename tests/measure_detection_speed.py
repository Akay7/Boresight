"""Measures what the fast detection path saves and what it costs.

Compares, per checked-in fixture, a session running the full pass on
every frame (detect.py before `speed-up-marker-detection`) with one
running through a `MarkerTracker`, as the server now does:

- decode, ms/frame: JPEG to colour then `cvtColor`, against decoding
  straight to greyscale, and whether the detections differ between them
- detect, ms/frame, and how many frames took the coarse pass
- markers found, and markers found by one path but not the other
- corner deviation, px: the tracker's corners against the full pass's
  for the same marker in the same frame
- corner error, px, against ground truth (synthetic_photo, which is
  replayed as a 20-frame still sequence)
- aim error and worst frame-to-frame delta error, mm, against the
  manifest (as tests/measure_detection.py computes them)

Detection time is measured on one OpenCV thread by default -- the
slower-PC case this exists for; `--threads 0` leaves OpenCV's default.

    uv run python tests/measure_detection_speed.py [--threads N]

Not part of the test suite; tests/test_detect_tracking.py asserts on
bounds, this prints the observed values they were chosen from.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
from measure_detection import _marker_corners_mm, _project, _solve

from boresight.detect import MarkerTracker, detect_markers

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VIDEO_FIXTURES = ("synthetic_video", "esp32cam_video", "close_range")
PHOTO_REPEATS = 20
TIMING_REPEATS = 15


def _decode_colour(jpeg: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(cv2.imdecode(jpeg, cv2.IMREAD_COLOR), cv2.COLOR_BGR2GRAY)


def _decode_grey(jpeg: np.ndarray) -> np.ndarray:
    return cv2.imdecode(jpeg, cv2.IMREAD_GRAYSCALE)


def _median_ms_per_item(run_once, items) -> float:
    """Median over repeats of one pass through `items`: the machine's
    other work lands in single repeats, which a mean would smear over
    every figure."""
    run_once(items[:1])
    passes = []
    for _ in range(TIMING_REPEATS):
        started = time.perf_counter()
        run_once(items)
        passes.append((time.perf_counter() - started) * 1000.0 / len(items))
    return float(np.median(passes))


def _ms_per_item(function, items) -> float:
    return _median_ms_per_item(lambda batch: [function(item) for item in batch], items)


def _ms_per_frame_tracked(frames) -> float:
    """A fresh tracker per pass: each repeat is a new session."""

    def run_once(batch):
        tracker = MarkerTracker()
        for frame in batch:
            tracker(frame)

    return _median_ms_per_item(run_once, frames)


def _by_id(markers) -> dict[int, np.ndarray]:
    return {marker.marker_id: marker.corners for marker in markers}


def _compare(full, tracked) -> dict:
    missed = extra = 0
    deviations = [0.0]
    for full_markers, tracked_markers in zip(full, tracked, strict=True):
        a, b = _by_id(full_markers), _by_id(tracked_markers)
        missed += len(a.keys() - b.keys())
        extra += len(b.keys() - a.keys())
        for marker_id in a.keys() & b.keys():
            deviations.extend(np.linalg.norm(a[marker_id] - b[marker_id], axis=1))
    return {"missed": missed, "extra": extra, "deviation_px": max(deviations)}


def _aim(detections, manifest, name) -> str:
    layout_mm = {int(k): tuple(v) for k, v in manifest["marker_layout_mm"].items()}
    size_mm = manifest["marker_size_mm"]
    image_size = tuple(manifest["image_size"])
    recovered, truth = [], []
    for entry, detected in zip(manifest["frames"], detections, strict=True):
        if not detected:
            continue
        result = _solve(detected, layout_mm, size_mm, image_size)
        if name == "close_range" and not result.aim_point_inside_hull:
            continue
        recovered.append(result.aim_point_mm)
        truth.append(entry["aim_point_screen_mm"])
    errors = np.linalg.norm(np.array(recovered) - np.array(truth), axis=1)
    text = f"aim max/mean {errors.max():.2f}/{errors.mean():.2f}mm"
    if name != "close_range":
        residuals = np.diff(recovered, axis=0) - np.diff(truth, axis=0)
        text += f"  delta max {np.linalg.norm(residuals, axis=1).max():.2f}mm"
    return text


def _report(label, frames, full, tracker, tracked, extra_line=""):
    total = sum(len(markers) for markers in full)
    comparison = _compare(full, tracked)
    print(f"  {label}")
    print(
        f"    detect  full {_ms_per_item(detect_markers, frames):5.2f}ms  "
        f"tracked {_ms_per_frame_tracked(frames):5.2f}ms/frame  "
        f"(coarse {tracker.coarse_passes}/{len(frames)} frames, "
        f"{tracker.coarse_misses} coarse misses)"
    )
    print(
        f"    markers {total} full, {sum(len(m) for m in tracked)} tracked "
        f"(missed {comparison['missed']}, extra {comparison['extra']})  "
        f"corner deviation max {comparison['deviation_px']:.3f}px"
    )
    if extra_line:
        print(f"    {extra_line}")


def measure_photo() -> None:
    metadata = json.loads((FIXTURES_DIR / "synthetic_photo.json").read_text())
    image = cv2.imread(str(FIXTURES_DIR / "synthetic_photo.png"), cv2.IMREAD_GRAYSCALE)
    layout_mm = {int(k): tuple(v) for k, v in metadata["marker_layout_mm"].items()}
    homography = np.array(metadata["ground_truth_homography"])
    frames = [image] * PHOTO_REPEATS

    def corner_errors(markers) -> str:
        errors = []
        for marker in markers:
            truth = _project(
                homography,
                np.array(
                    _marker_corners_mm(
                        layout_mm[marker.marker_id], metadata["marker_size_mm"]
                    )
                )
                - 0.5,
            )
            errors.extend(np.linalg.norm(marker.corners - truth, axis=1))
        return f"{np.mean(errors):.3f}/{np.max(errors):.3f}px"

    tracker = MarkerTracker()
    tracked = [tracker(frame) for frame in frames]
    full = [detect_markers(frame) for frame in frames]
    _report(
        "synthetic_photo (1920x1080, still x20)",
        frames,
        full,
        tracker,
        tracked,
        f"corner error mean/max  full {corner_errors(full[0])}  "
        f"tracked (coarse frame) {corner_errors(tracked[-1])}",
    )


def measure_video(name: str) -> None:
    directory = FIXTURES_DIR / name
    manifest = json.loads((directory / "manifest.json").read_text())
    jpegs = [
        np.frombuffer((directory / entry["file"]).read_bytes(), dtype=np.uint8)
        for entry in manifest["frames"]
    ]
    frames = [_decode_colour(jpeg) for jpeg in jpegs]
    grey_frames = [_decode_grey(jpeg) for jpeg in jpegs]

    full = [detect_markers(frame) for frame in frames]
    tracker = MarkerTracker()
    tracked = [tracker(frame) for frame in frames]
    decode_change = _compare(full, [detect_markers(f) for f in grey_frames])

    width, height = manifest["image_size"]
    _report(
        f"{name} ({int(width)}x{int(height)}, {len(frames)} frames)",
        frames,
        full,
        tracker,
        tracked,
        f"decode  colour+cvtColor {_ms_per_item(_decode_colour, jpegs):5.2f}ms  "
        f"greyscale {_ms_per_item(_decode_grey, jpegs):5.2f}ms/frame  "
        f"(detections: missed {decode_change['missed']}, extra "
        f"{decode_change['extra']}, corner deviation max "
        f"{decode_change['deviation_px']:.3f}px)\n"
        f"    full    {_aim(full, manifest, name)}\n"
        f"    tracked {_aim(tracked, manifest, name)}",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--threads",
        type=int,
        default=1,
        help="OpenCV threads; 0 keeps OpenCV's default (default: 1)",
    )
    args = parser.parse_args()
    if args.threads > 0:
        cv2.setNumThreads(args.threads)
    print(f"OpenCV {cv2.__version__}, {cv2.getNumThreads()} thread(s)")
    measure_photo()
    for name in VIDEO_FIXTURES:
        measure_video(name)


if __name__ == "__main__":
    main()
