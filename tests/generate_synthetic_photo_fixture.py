"""Generates the checked-in synthetic "photo" fixture used by
test_solve_e2e_realistic.py: tests/fixtures/synthetic_photo.png plus its
ground-truth metadata, tests/fixtures/synthetic_photo.json.

Run manually when the fixture needs to change -- e.g. a deliberate
change to the degradation model or marker layout:

    uv run python tests/generate_synthetic_photo_fixture.py

Not run as part of the test suite. The fixture is checked into the repo
rather than regenerated per test run so the e2e test is a true
regression test: if detect.py or solve.py changes and produces a
different result against this exact image, that's a real signal, not an
artifact of a freshly-rerolled random seed.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

FIXTURE_DIR = Path(__file__).parent / "fixtures"
IMAGE_PATH = FIXTURE_DIR / "synthetic_photo.png"
METADATA_PATH = FIXTURE_DIR / "synthetic_photo.json"

IMAGE_SIZE = (1920.0, 1080.0)
CANVAS_SIZE = (800, 800)
MARKER_SIZE_MM = 80.0

MARKER_LAYOUT_MM = {
    0: (0.0, 0.0),
    1: (620.0, 0.0),
    2: (620.0, 620.0),
    3: (0.0, 620.0),
    4: (310.0, 0.0),
    5: (620.0, 310.0),
    6: (310.0, 620.0),
    7: (0.0, 310.0),
}

GROUND_TRUTH_HOMOGRAPHY = np.array(
    [
        [1.2, 0.02, 150.0],
        [-0.01, 1.15, 100.0],
        [0.0002, 0.0001, 1.0],
    ],
    dtype=np.float64,
)

# Uneven exposure, blur, and sensor noise: the failure modes README's
# "Known failure modes" section names as dominant in practice.
DEGRADATION = {
    "seed": 0,
    "blur_kernel": 5,
    "blur_sigma": 1.2,
    "noise_sigma": 6.0,
    "gradient_lo": 0.75,
    "gradient_hi": 1.05,
}


def _render_clean_warp() -> np.ndarray:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    canvas = np.full(CANVAS_SIZE[::-1], 255, dtype=np.uint8)

    for marker_id, (x, y) in MARKER_LAYOUT_MM.items():
        marker_img = cv2.aruco.generateImageMarker(
            dictionary, marker_id, int(MARKER_SIZE_MM)
        )
        x, y = int(x), int(y)
        canvas[y : y + marker_img.shape[0], x : x + marker_img.shape[1]] = marker_img

    return cv2.warpPerspective(
        canvas,
        GROUND_TRUTH_HOMOGRAPHY,
        (int(IMAGE_SIZE[0]), int(IMAGE_SIZE[1])),
        borderValue=255,
    )


def _degrade(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    _, width = image.shape
    working = image.astype(np.float64)

    gradient = np.linspace(
        DEGRADATION["gradient_hi"], DEGRADATION["gradient_lo"], width
    )
    working *= gradient[np.newaxis, :]

    kernel = DEGRADATION["blur_kernel"]
    working = cv2.GaussianBlur(
        working, (kernel, kernel), sigmaX=DEGRADATION["blur_sigma"]
    )

    working += rng.normal(loc=0.0, scale=DEGRADATION["noise_sigma"], size=working.shape)

    return np.clip(working, 0, 255).astype(np.uint8)


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(seed=DEGRADATION["seed"])
    image = _degrade(_render_clean_warp(), rng)
    cv2.imwrite(str(IMAGE_PATH), image, [cv2.IMWRITE_PNG_COMPRESSION, 9])

    metadata = {
        "image_size": list(IMAGE_SIZE),
        "marker_size_mm": MARKER_SIZE_MM,
        "marker_layout_mm": {str(k): list(v) for k, v in MARKER_LAYOUT_MM.items()},
        "ground_truth_homography": GROUND_TRUTH_HOMOGRAPHY.tolist(),
        "degradation": DEGRADATION,
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2) + "\n")

    print(f"Wrote {IMAGE_PATH} and {METADATA_PATH}")


if __name__ == "__main__":
    main()
