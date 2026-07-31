"""End-to-end test of the full pipeline over a checked-in synthetic video.

`add-homography-solver` deferred the video case explicitly: solve.py was
only ever exercised one frame at a time, which says nothing about how
its output behaves over a sequence. A stateless solver can be correct on
every frame in isolation and still produce a trajectory that jitters,
because each frame's homography is fitted independently.

tests/fixtures/synthetic_video/ is a Blender render of a TV -- lit 16:9
panel, markers printed on cardstock stuck to the bezel around it, dim
room behind -- with the camera sweeping across the panel. It is the
closest available stand-in for real footage: markers are not printed and
no camera or video transport exists yet (README Milestones).

What makes it worth the Blender dependency is the ground truth. Each
frame's aim point is computed from the rendering camera's own pose --
where its optical axis meets the panel plane -- with no homography
involved, so this checks solve.py against an independent reference
rather than against its own arithmetic.

See generate_synthetic_video_fixture.py to regenerate (needs Blender;
this test does not).
"""

import json
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from boresight.detect import detect_markers
from boresight.solve import solve

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "synthetic_video"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"

# Observed against this fixture: per-frame error peaks at ~1.5mm and
# consecutive-frame deltas track ground truth to ~1.2mm. 4mm leaves
# roughly 3x margin without masking a real regression -- on this 1220mm
# panel it is 0.3% of screen width, a few pixels of cursor travel.
AIM_TOLERANCE_MM = 4.0
DELTA_TOLERANCE_MM = 4.0

# detect+solve runs ~2ms/frame here. 150ms/frame is a loose regression
# guard against something pathological (an accidental O(n^2), a
# per-call model reload), NOT a real-time latency claim -- README is
# explicit that actual latency has to be measured against real hardware
# and a real network hop, neither of which this fixture has.
MAX_MS_PER_FRAME = 150.0


def _marker_corners_mm(
    top_left: tuple[float, float], size: float
) -> list[tuple[float, float]]:
    """Clockwise from top-left, matching cv2.aruco's detected corner order."""
    x, y = top_left
    return [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]


@pytest.fixture(scope="module")
def manifest() -> dict:
    assert MANIFEST_PATH.exists(), (
        f"video fixture manifest missing at {MANIFEST_PATH}; regenerate with "
        "`uv run python -m tests.generate_synthetic_video_fixture` (needs Blender)"
    )
    return json.loads(MANIFEST_PATH.read_text())


@pytest.fixture(scope="module")
def solved_track(manifest: dict) -> dict:
    """Runs the whole pipeline once over every frame, in order.

    Shared across the assertions below so the sequence is solved once,
    and so the timing figure covers the same work the other checks
    assert on.
    """
    layout_mm = {
        int(marker_id): tuple(top_left)
        for marker_id, top_left in manifest["marker_layout_mm"].items()
    }
    marker_size_mm = manifest["marker_size_mm"]
    image_size = tuple(manifest["image_size"])

    frames = []
    for entry in manifest["frames"]:
        image = cv2.imread(str(FIXTURE_DIR / entry["file"]), cv2.IMREAD_COLOR)
        assert image is not None, f"missing fixture frame {entry['file']}"
        frames.append(image)

    recovered = []
    detected_counts = []
    started = time.perf_counter()
    for image in frames:
        # README's pipeline starts by going to greyscale; the fixture
        # frames are colour because that is what a camera hands over.
        grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        detected = detect_markers(grey)
        detected_counts.append(len(detected))

        correspondences = []
        for marker in detected:
            known_corners_mm = _marker_corners_mm(
                layout_mm[marker.marker_id], marker_size_mm
            )
            for screen_point, image_point in zip(
                known_corners_mm, marker.corners, strict=True
            ):
                correspondences.append(
                    (screen_point, (float(image_point[0]), float(image_point[1])))
                )

        recovered.append(solve(correspondences, image_size).aim_point_mm)
    elapsed_s = time.perf_counter() - started

    return {
        "recovered": np.array(recovered, dtype=np.float64),
        "ground_truth": np.array(
            [entry["aim_point_screen_mm"] for entry in manifest["frames"]],
            dtype=np.float64,
        ),
        "detected_counts": detected_counts,
        "elapsed_s": elapsed_s,
        "frame_count": len(frames),
    }


def test_every_frame_is_solvable(solved_track: dict):
    assert solved_track["frame_count"] > 1, "a video fixture needs multiple frames"
    # The pipeline's real floor is one fully visible marker: four
    # corners are enough to solve. Asserting all eight would be
    # asserting the camera path never clips one, which is a property of
    # the fixture, not of the code under test.
    assert min(solved_track["detected_counts"]) >= 1


def test_each_frame_matches_its_own_ground_truth(solved_track: dict):
    errors = np.linalg.norm(
        solved_track["recovered"] - solved_track["ground_truth"], axis=1
    )
    worst = int(np.argmax(errors))
    assert errors.max() == pytest.approx(0.0, abs=AIM_TOLERANCE_MM), (
        f"frame {worst + 1} recovered {solved_track['recovered'][worst]} "
        f"vs ground truth {solved_track['ground_truth'][worst]} "
        f"({errors[worst]:.2f}mm off)"
    )


def test_consecutive_frames_track_the_known_camera_motion(solved_track: dict):
    """The temporal-coherence check.

    Compares measured frame-to-frame deltas against ground-truth
    deltas rather than against a bare "did it jump more than X"
    threshold: the camera genuinely moves tens of mm per frame here, so
    a fixed jump limit would either permit real discontinuities or flag
    the intended motion.
    """
    recovered_deltas = np.diff(solved_track["recovered"], axis=0)
    truth_deltas = np.diff(solved_track["ground_truth"], axis=0)
    residuals = np.linalg.norm(recovered_deltas - truth_deltas, axis=1)

    # Guards the comparison itself: if the fixture's camera barely moved,
    # matching deltas would be trivially satisfied and prove nothing.
    assert np.linalg.norm(truth_deltas, axis=1).min() > DELTA_TOLERANCE_MM

    worst = int(np.argmax(residuals))
    assert residuals.max() == pytest.approx(0.0, abs=DELTA_TOLERANCE_MM), (
        f"frames {worst + 1}->{worst + 2} moved by "
        f"{recovered_deltas[worst]} but ground truth moved by "
        f"{truth_deltas[worst]} ({residuals[worst]:.2f}mm of unexplained jump)"
    )


def test_per_frame_cost_stays_sane(solved_track: dict):
    ms_per_frame = solved_track["elapsed_s"] * 1000.0 / solved_track["frame_count"]
    assert ms_per_frame < MAX_MS_PER_FRAME, (
        f"detect+solve took {ms_per_frame:.1f}ms/frame, over the "
        f"{MAX_MS_PER_FRAME}ms regression ceiling"
    )
