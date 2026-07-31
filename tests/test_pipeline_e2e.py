"""End-to-end: rendered frames in, cursor moves out.

The solver decks already assert that `solve.py` recovers each frame's
aim point. These assert the rest of the path -- that the shipped
`config/markers.toml` is the right layout for these frames, that
detection output is paired with it correctly, that normalization uses
the configured screen size, and that emission happens exactly when it
should.

One measured caveat, because it shapes what the assertions below are
worth: with the whole layout in frame, accuracy is remarkably
insensitive to how the correspondences are paired. Reversing
`Marker.corners_mm` to counter-clockwise -- a reflection of every
marker about its own diagonal -- costs only 1.77mm here, comfortably
inside the tolerance, because RANSAC averages a per-marker permutation
away across 32 correspondences. The sparse close-range assertions at
the bottom of this file *do* catch it, since there the permutation is
the entire fit. Corner order is pinned exactly in
`test_marker_map.py`; do not rely on the full-visibility deck for it.

Nothing is rendered. Both fixtures are checked in.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boresight.inject import FakeCursorBackend
from boresight.marker_map import load_marker_map
from boresight.pipeline import DEFAULT_CONFIG_PATH, AimPipeline, FrameOutcome, replay

VIDEO_DIR = Path(__file__).parent / "fixtures" / "synthetic_video"
CLOSE_RANGE_DIR = Path(__file__).parent / "fixtures" / "close_range"

# The solver deck holds itself to 4.0mm on this fixture. The pipeline
# adds no arithmetic to the aim point beyond dividing by the screen
# size, so it is held to the same figure -- converted per axis, since
# normalized coordinates are not isotropic on a 16:9 panel.
AIM_TOLERANCE_MM = 4.0

MARKER_COUNT = 8


def _manifest(fixture_dir: Path) -> dict:
    path = fixture_dir / "manifest.json"
    assert path.exists(), (
        f"fixture manifest missing at {path}; regenerate with "
        "`uv run python -m tests.generate_synthetic_video_fixture` (needs Blender)"
    )
    return json.loads(path.read_text())


def _run(fixture_dir: Path) -> tuple[list, FakeCursorBackend, dict]:
    manifest = _manifest(fixture_dir)
    backend = FakeCursorBackend()
    pipeline = AimPipeline(load_marker_map(DEFAULT_CONFIG_PATH), backend)
    return replay(fixture_dir, pipeline), backend, manifest


@pytest.fixture(scope="module")
def video_run() -> tuple[list, FakeCursorBackend, dict]:
    return _run(VIDEO_DIR)


@pytest.fixture(scope="module")
def close_range_run() -> tuple[list, FakeCursorBackend, dict]:
    return _run(CLOSE_RANGE_DIR)


# --- Full visibility -------------------------------------------------


def test_every_video_frame_solves(video_run) -> None:
    results, _backend, manifest = video_run

    assert len(results) == len(manifest["frames"])
    assert all(result.outcome is FrameOutcome.SOLVED for result in results)
    assert all(result.markers_mapped == MARKER_COUNT for result in results)
    assert all(result.markers_ignored == 0 for result in results)


def test_emitted_track_matches_the_manifest_ground_truth(video_run) -> None:
    """The ground truth here comes from the rendering camera's own pose --
    where its optical axis meets the panel -- with no homography
    involved, so this compares the pipeline against an independent
    reference rather than against its own arithmetic."""
    results, _backend, manifest = video_run
    screen_mm = manifest["screen_size_mm"]

    for result, entry in zip(results, manifest["frames"], strict=True):
        truth_mm = entry["aim_point_screen_mm"]
        # Back through the normalization, so this asserts on what was
        # actually emitted rather than on the millimetre value beside it.
        emitted_mm = [
            coordinate * span
            for coordinate, span in zip(result.position, screen_mm, strict=True)
        ]

        assert emitted_mm == pytest.approx(truth_mm, abs=AIM_TOLERANCE_MM), (
            f"{entry['file']}: emitted {emitted_mm} mm, expected {truth_mm} mm"
        )


def test_one_move_is_emitted_per_solved_frame(video_run) -> None:
    results, backend, _manifest = video_run

    assert len(backend.calls) == len(results)
    assert backend.calls == [result.position for result in results]


def test_no_video_frame_is_clamped(video_run) -> None:
    """Every ground-truth aim point in this sequence is on the panel. A
    clamp here would mean the aim point left the screen, which would
    make the accuracy assertion above meaningless for that frame."""
    results, _backend, _manifest = video_run

    assert not any(result.clamped for result in results)


def test_conditioning_is_propagated_not_invented(video_run) -> None:
    """With the whole layout in frame the aim point is always inside the
    marker hull. If this flag were hardcoded rather than passed through
    from the solver, the close-range assertions below would fail."""
    results, _backend, _manifest = video_run

    assert all(result.aim_point_inside_hull for result in results)
    assert all(result.aim_point_hull_distance_mm > 0.0 for result in results)


# --- Partial visibility ----------------------------------------------


def test_close_range_replay_completes(close_range_run) -> None:
    """Frames with nothing to solve from must not raise. Half this
    fixture is unsolvable by construction."""
    results, _backend, manifest = close_range_run

    assert len(results) == len(manifest["frames"])


def test_frames_with_no_markers_emit_nothing(close_range_run) -> None:
    results, backend, manifest = close_range_run

    unsolvable = [
        result
        for result, entry in zip(results, manifest["frames"], strict=True)
        if entry["expected_markers_when_generated"] == 0
    ]

    assert unsolvable, "fixture no longer contains a zero-marker pose"
    assert all(result.outcome is FrameOutcome.NO_MARKERS for result in unsolvable)
    assert all(result.markers_detected == 0 for result in unsolvable)
    assert len(backend.calls) == len(results) - len(unsolvable)


def test_solvable_close_range_frames_still_emit(close_range_run) -> None:
    """A single marker at close range gives four points and eight degrees
    of freedom, so it fits exactly and is flagged as extrapolated -- but
    it is still emitted. Suppressing flagged solves would blank the
    cursor for exactly the poses the midpoint markers exist to cover."""
    results, _backend, manifest = close_range_run

    solvable = [
        result
        for result, entry in zip(results, manifest["frames"], strict=True)
        if entry["expected_markers_when_generated"] > 0
    ]

    assert solvable, "fixture no longer contains a solvable close-range pose"
    assert all(result.outcome is FrameOutcome.SOLVED for result in solvable)
    assert all(result.emitted for result in solvable)


def test_sparse_close_range_solves_are_flagged(close_range_run) -> None:
    """The one- and two-marker poses aim well outside the visible
    markers. That has to reach the caller, since it is the only signal
    distinguishing them from the full-visibility case."""
    results, _backend, manifest = close_range_run

    sparse = [
        result
        for result, entry in zip(results, manifest["frames"], strict=True)
        if 0 < entry["expected_markers_when_generated"] <= 2
    ]

    assert sparse, "fixture no longer contains a sparse solvable pose"
    assert all(result.aim_point_inside_hull is False for result in sparse)
    assert all(result.aim_point_hull_distance_mm < 0.0 for result in sparse)
