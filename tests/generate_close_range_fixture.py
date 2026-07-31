"""Generates the checked-in close-range fixture used by
test_solve_close_range.py: tests/fixtures/close_range/.

    uv run python -m tests.generate_close_range_fixture

Requires Blender (`blender-5.2`, override with $BORESIGHT_BLENDER); the
test suite does not.

Same TV scene, ground-truth derivation, degradation model and JPEG
encoding as the video fixture -- it reuses that module's
`render_sequence()` and `blender_video_scene.py` unchanged. The only
difference is where the camera stands: close to the panel, where the
bezel markers fall outside the frustum.

That is the situation this fixture exists to capture. A player standing
near a large screen with a 45-degree-FOV camera cannot see the whole
marker layout -- and aiming at screen centre from close in, cannot see
*any* of it, since every marker is on the bezel outside the panel. The
poses below were chosen by rendering candidates and keeping a spread
that yields 0, 1, 2 and 3 visible markers, so the test deck covers
"cannot solve at all" through "solvable but extrapolating" through
"still well-conditioned".
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import cv2
import numpy as np

from tests.generate_synthetic_video_fixture import (
    BLENDER_BINARY,
    CAMERA_FOV_DEG,
    DEGRADATION,
    JPEG_QUALITY,
    MARKER_LAYOUT_MM,
    MARKER_SIZE_MM,
    RESOLUTION,
    SCREEN_SIZE_MM,
    TESTS_DIR,
    _degrade,
    render_sequence,
)

FIXTURE_DIR = TESTS_DIR / "fixtures" / "close_range"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
BLEND_PATH = FIXTURE_DIR / "scene.blend"

# Each entry is its own camera pose rather than a point on a sweep:
# this deck is about visibility conditions, not motion. A keyframe on
# every frame means Blender's interpolation never applies and each frame
# renders exactly the pose given.
#
# `expect_markers` records what the render actually produced when these
# poses were chosen; the test asserts against the manifest, not against
# this, but a mismatch here on regeneration means the scene moved.
#   label, aim x/y (screen mm), camera x/y/z (world mm), expect_markers
_POSE_TABLE = [
    ("centre, 1200mm", (610.0, 343.0), (0.0, -1200.0, 0.0), 0),
    ("centre, 1600mm", (610.0, 343.0), (0.0, -1600.0, 0.0), 0),
    ("left edge, 1300mm", (80.0, 343.0), (-400.0, -1300.0, 0.0), 1),
    ("top edge, 1400mm", (610.0, 80.0), (0.0, -1400.0, 300.0), 1),
    ("top-left, 1200mm", (150.0, 100.0), (-350.0, -1200.0, 250.0), 2),
    ("bottom-right, 1300mm", (1100.0, 600.0), (400.0, -1300.0, -250.0), 2),
    ("top-left, 1500mm", (150.0, 100.0), (-350.0, -1500.0, 250.0), 3),
]

KEYFRAMES = [
    {
        "frame": index + 1,
        "aim_screen_mm": list(aim),
        "camera_position": list(position),
    }
    for index, (_, aim, position, _) in enumerate(_POSE_TABLE)
]
FRAME_COUNT = len(_POSE_TABLE)


def main() -> None:
    if FIXTURE_DIR.exists():
        shutil.rmtree(FIXTURE_DIR)
    FIXTURE_DIR.mkdir(parents=True)

    with tempfile.TemporaryDirectory() as tmp:
        raw_dir, ground_truth = render_sequence(
            Path(tmp), KEYFRAMES, FRAME_COUNT, BLEND_PATH
        )

        frames = []
        for entry, (label, _, _, expected_markers) in zip(
            ground_truth, _POSE_TABLE, strict=True
        ):
            frame_number = entry["frame"]
            raw_path = raw_dir / f"frame_{frame_number:04d}.png"
            raw_image = cv2.imread(str(raw_path), cv2.IMREAD_COLOR)
            if raw_image is None:
                raise RuntimeError(f"Blender did not produce {raw_path}")

            rng = np.random.default_rng(seed=DEGRADATION["base_seed"] + frame_number)
            degraded = _degrade(raw_image, rng)

            filename = f"frame_{frame_number:04d}.jpg"
            cv2.imwrite(
                str(FIXTURE_DIR / filename),
                degraded,
                [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
            )
            frames.append(
                {
                    "frame": frame_number,
                    "file": filename,
                    "label": label,
                    "expected_markers_when_generated": expected_markers,
                    "aim_point_screen_mm": entry["aim_point_screen_mm"],
                }
            )

    manifest = {
        "image_size": [float(RESOLUTION[0]), float(RESOLUTION[1])],
        "screen_size_mm": list(SCREEN_SIZE_MM),
        "marker_size_mm": MARKER_SIZE_MM,
        "marker_layout_mm": {str(k): list(v) for k, v in MARKER_LAYOUT_MM.items()},
        "camera_fov_deg": CAMERA_FOV_DEG,
        "degradation": DEGRADATION,
        "jpeg_quality": JPEG_QUALITY,
        "blender": BLENDER_BINARY,
        "frames": frames,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"Wrote {len(frames)} frames, {MANIFEST_PATH}, and {BLEND_PATH}")


if __name__ == "__main__":
    main()
