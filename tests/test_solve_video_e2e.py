"""DECK A (full visibility): the pipeline over a checked-in synthetic video.

Evidence for: what the system achieves with the whole marker layout in
frame. Tolerances here are deliberately tight -- this deck is the
statement of best-case accuracy, and must not be loosened to
accommodate the partial-visibility deck (test_solve_partial_markers.py),
which measures a different and much weaker regime.


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

The same scene and sweep is also rendered as an ESP32-CAM sees it
(tests/fixtures/esp32cam_video/: 1024x768, 4:3, wider lens, noisier
sensor, heavier JPEG), and every check here runs against both, each
against its own tolerances. The phone fixture's are the statement of
best-case accuracy; the device fixture's say what the firmware's default
resolution costs.

See generate_synthetic_video_fixture.py to regenerate (needs Blender;
this test does not).
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytest

from boresight.detect import detect_markers
from boresight.solve import solve

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@dataclass(frozen=True)
class VideoFixture:
    name: str
    aim_tolerance_mm: float
    delta_tolerance_mm: float

    @property
    def directory(self) -> Path:
        return FIXTURES_DIR / self.name

    @property
    def manifest_path(self) -> Path:
        return self.directory / "manifest.json"


FIXTURES = [
    # Observed: per-frame error peaks at ~1.5mm and consecutive-frame
    # deltas track ground truth to ~1.2mm. 4mm leaves roughly 3x margin
    # without masking a real regression -- on this 1220mm panel it is
    # 0.3% of screen width, a few pixels of cursor travel.
    VideoFixture("synthetic_video", aim_tolerance_mm=4.0, delta_tolerance_mm=4.0),
    # Observed at the firmware's default 1024x768: per-frame error peaks
    # at ~2.9mm and deltas track ground truth to ~1.5mm, with 6-8 of the 8
    # markers found per frame (~25px across). About 2x margin on the aim,
    # as the lower resolution earns less than the phone's 3x: 6mm is 0.5%
    # of this panel's width. At 800x600 the same sweep reached 276mm,
    # which is why that is no longer the default.
    VideoFixture("esp32cam_video", aim_tolerance_mm=6.0, delta_tolerance_mm=4.0),
]

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


@pytest.fixture(scope="module", params=FIXTURES, ids=lambda fixture: fixture.name)
def video(request: pytest.FixtureRequest) -> VideoFixture:
    return request.param


@pytest.fixture(scope="module")
def manifest(video: VideoFixture) -> dict:
    assert video.manifest_path.exists(), (
        f"video fixture manifest missing at {video.manifest_path}; regenerate "
        "with `uv run python -m tests.generate_synthetic_video_fixture` "
        "(needs Blender; add `--profile esp32cam` for esp32cam_video)"
    )
    return json.loads(video.manifest_path.read_text())


@pytest.fixture(scope="module")
def solved_track(video: VideoFixture, manifest: dict) -> dict:
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
        image = cv2.imread(str(video.directory / entry["file"]), cv2.IMREAD_COLOR)
        assert image is not None, f"missing fixture frame {entry['file']}"
        frames.append(image)

    recovered = []
    detected_counts = []
    inside_hull = []
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

        result = solve(correspondences, image_size)
        recovered.append(result.aim_point_mm)
        inside_hull.append(result.aim_point_inside_hull)
    elapsed_s = time.perf_counter() - started

    return {
        "recovered": np.array(recovered, dtype=np.float64),
        "ground_truth": np.array(
            [entry["aim_point_screen_mm"] for entry in manifest["frames"]],
            dtype=np.float64,
        ),
        "detected_counts": detected_counts,
        "inside_hull": inside_hull,
        "elapsed_s": elapsed_s,
        "frame_count": len(frames),
    }


def test_every_solve_is_well_conditioned(solved_track: dict):
    """States the good case explicitly rather than leaving it implied.

    With the layout surrounding the panel, the aim point is enclosed by
    the marker corners on every frame, so it is interpolated. That is
    *why* this deck's tolerances can be tight, and it is the property
    the partial-visibility deck shows the system losing.
    """
    assert all(solved_track["inside_hull"])


def test_every_frame_is_solvable(solved_track: dict):
    assert solved_track["frame_count"] > 1, "a video fixture needs multiple frames"
    # The pipeline's real floor is one fully visible marker: four
    # corners are enough to solve. Asserting all eight would be
    # asserting the camera path never clips one, which is a property of
    # the fixture, not of the code under test.
    assert min(solved_track["detected_counts"]) >= 1


def test_each_frame_matches_its_own_ground_truth(
    video: VideoFixture, solved_track: dict
):
    errors = np.linalg.norm(
        solved_track["recovered"] - solved_track["ground_truth"], axis=1
    )
    worst = int(np.argmax(errors))
    assert errors.max() == pytest.approx(0.0, abs=video.aim_tolerance_mm), (
        f"frame {worst + 1} recovered {solved_track['recovered'][worst]} "
        f"vs ground truth {solved_track['ground_truth'][worst]} "
        f"({errors[worst]:.2f}mm off)"
    )


def test_consecutive_frames_track_the_known_camera_motion(
    video: VideoFixture, solved_track: dict
):
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
    assert np.linalg.norm(truth_deltas, axis=1).min() > video.delta_tolerance_mm

    worst = int(np.argmax(residuals))
    assert residuals.max() == pytest.approx(0.0, abs=video.delta_tolerance_mm), (
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
