"""DECK B (partial visibility): real close-range renders.

Evidence for: what happens when the camera is close enough that the
bezel markers physically leave the frustum -- the player-stands-near-the-
TV case. Where test_solve_partial_markers.py constructs partial
visibility by subsetting detections (exact control over geometry), this
module gets it the honest way: markers are missing because the camera
cannot see them, and detection runs on frames where that is true.

A finding worth stating, because it shapes what these tests assert:
being flagged as extrapolated does NOT mean the answer is wrong. These
close-range frames are flagged (the aim point sits well outside the one
or two visible markers) yet land within a few mm, because a marker seen
from 1.3m spans many more pixels than one seen from 3m, so its corners
localise far more precisely and the extrapolation is shorter in screen
mm. Compare the far-range single-marker case, which reaches ~2m of
error. The flag marks solves whose accuracy is *unguaranteed*, not
solves that are bad -- so this deck asserts the flag and the
raise-vs-return behaviour, and does not assert that flagged frames are
inaccurate.
"""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from boresight.detect import detect_markers
from boresight.solve import InsufficientCorrespondencesError, solve

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "close_range"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"


def _marker_corners_mm(
    top_left: tuple[float, float], size: float
) -> list[tuple[float, float]]:
    x, y = top_left
    return [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]


@pytest.fixture(scope="module")
def close_range_frames() -> list[dict]:
    assert MANIFEST_PATH.exists(), (
        f"close-range fixture missing at {MANIFEST_PATH}; regenerate with "
        "`uv run python -m tests.generate_close_range_fixture` (needs Blender)"
    )
    manifest = json.loads(MANIFEST_PATH.read_text())
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
        grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        detected = detect_markers(grey)

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

        frames.append(
            {
                "label": entry["label"],
                "expected_markers": entry["expected_markers_when_generated"],
                "detected_count": len(detected),
                "correspondences": correspondences,
                "ground_truth": entry["aim_point_screen_mm"],
                "image_size": image_size,
            }
        )
    return frames


def test_the_fixture_still_shows_what_it_was_built_to_show(
    close_range_frames: list[dict],
):
    """Guards the fixture itself.

    If the scene, detector, or degradation changes such that these poses
    stop yielding the marker counts they were chosen for, the rest of
    this deck would still pass while testing something else entirely.
    """
    for frame in close_range_frames:
        assert frame["detected_count"] == frame["expected_markers"], (
            f"{frame['label']}: expected {frame['expected_markers']} markers "
            f"when the fixture was built, detector now finds "
            f"{frame['detected_count']}"
        )


def test_close_range_centre_aim_sees_no_markers_and_cannot_be_solved(
    close_range_frames: list[dict],
):
    """The working-distance floor, as a rendered fact.

    Every marker is on the bezel outside the panel, so aiming at screen
    centre from close in puts all of them outside the frustum. There is
    nothing to solve from -- this is a hardware/layout limit, not
    something the solver can fix, and README's suggested inner marker
    ring is the remedy.
    """
    blind = [f for f in close_range_frames if f["detected_count"] == 0]
    assert blind, "fixture no longer contains a zero-marker frame"

    for frame in blind:
        with pytest.raises(InsufficientCorrespondencesError):
            solve(frame["correspondences"], frame["image_size"])


def test_frames_with_some_markers_still_solve(close_range_frames: list[dict]):
    """Partial visibility must degrade, not fail."""
    partial = [f for f in close_range_frames if f["detected_count"] >= 1]
    assert partial, "fixture no longer contains a partially-visible frame"

    for frame in partial:
        result = solve(frame["correspondences"], frame["image_size"])
        assert np.isfinite(result.aim_point_mm).all()


def test_conditioning_matches_the_visible_geometry(close_range_frames: list[dict]):
    """The flag tracks whether the markers actually enclose the aim point.

    One or two markers on a single bezel edge cannot enclose an aim
    point out on the panel, so those frames report extrapolation. Three
    markers spanning two edges do enclose it, and report interpolation
    even though this is still 'partial' visibility -- which is the point:
    the signal is about geometry, not marker count.
    """
    enclosing = 0
    extrapolating = 0
    for frame in close_range_frames:
        if frame["detected_count"] < 1:
            continue
        result = solve(frame["correspondences"], frame["image_size"])

        if result.aim_point_inside_hull:
            enclosing += 1
            assert result.aim_point_hull_distance_mm >= 0.0
        else:
            extrapolating += 1
            assert result.aim_point_hull_distance_mm < 0.0

    assert extrapolating > 0, "expected close-range frames that extrapolate"
    assert enclosing > 0, (
        "expected at least one close-range frame whose visible markers still "
        "enclose the aim point -- otherwise this deck only shows one outcome"
    )


def test_a_close_range_enclosing_frame_is_accurate(close_range_frames: list[dict]):
    """Partial visibility is not itself a problem when the geometry holds."""
    checked = 0
    for frame in close_range_frames:
        if frame["detected_count"] < 1:
            continue
        result = solve(frame["correspondences"], frame["image_size"])
        if not result.aim_point_inside_hull:
            continue
        checked += 1
        error = float(
            np.hypot(
                result.aim_point_mm[0] - frame["ground_truth"][0],
                result.aim_point_mm[1] - frame["ground_truth"][1],
            )
        )
        # Observed 1.24mm on the 3-marker frame; 5mm leaves margin.
        assert error < 5.0, f"{frame['label']}: {error:.2f}mm"
    assert checked > 0
