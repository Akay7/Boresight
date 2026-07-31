"""DECK B (partial visibility): only some of the marker layout in frame.

Evidence for: how the solver behaves when the player stands close, aims
off-axis, or otherwise loses part of the layout -- the normal condition
in real play, and the one README's edge-midpoint markers exist for.

This deck asserts different things from Deck A, deliberately. Where the
geometry supports an accurate answer it asserts accuracy; where it does
not, it asserts the result is *flagged*, because no solver can
recover an accurate aim point by extrapolating a homography far outside
the points that fitted it. Demanding accuracy there would be demanding
something the geometry cannot deliver.

Partial visibility is produced here by subsetting the detections from
the full-visibility video fixture, which allows specific geometries
(opposite edges, one edge, a single marker) to be hit exactly. The
companion module test_solve_close_range.py covers the same regime the
other way round -- real renders where markers genuinely leave frame.
"""

import itertools
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from boresight.detect import detect_markers
from boresight.solve import InsufficientCorrespondencesError, solve

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "synthetic_video"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"

# Marker ids by position in the layout (see the fixture generator).
CORNERS = (0, 1, 2, 3)
TOP_EDGE = (0, 4, 1)
OPPOSITE_MIDPOINTS = (7, 5)

# Every inside-hull solve observed across all 4844 subset x frame
# combinations landed within 18.3mm; 25mm leaves margin. This is the
# bound the conditioning flag actually buys you.
INSIDE_HULL_BOUND_MM = 25.0

# A well-spread subset (the four corners -- half the layout) is
# essentially as good as full visibility: 1.95mm observed vs 1.59mm.
WELL_CONDITIONED_TOLERANCE_MM = 4.0

# Locks in the *currently observed* badness of single-marker solves
# (median 145mm, max 2037mm on a 1220mm panel). Not a desired property:
# if the solvePnP-with-intrinsics path ever lands, this fails loudly and
# should be revisited rather than quietly passing.
SPARSE_ERROR_IS_STILL_BAD_MM = 100.0


def _marker_corners_mm(
    top_left: tuple[float, float], size: float
) -> list[tuple[float, float]]:
    x, y = top_left
    return [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]


@pytest.fixture(scope="module")
def fixture_data() -> dict:
    assert MANIFEST_PATH.exists(), (
        f"video fixture missing at {MANIFEST_PATH}; regenerate with "
        "`uv run python -m tests.generate_synthetic_video_fixture`"
    )
    manifest = json.loads(MANIFEST_PATH.read_text())
    layout_mm = {
        int(marker_id): tuple(top_left)
        for marker_id, top_left in manifest["marker_layout_mm"].items()
    }

    frames = []
    for entry in manifest["frames"]:
        image = cv2.imread(str(FIXTURE_DIR / entry["file"]), cv2.IMREAD_COLOR)
        assert image is not None, f"missing fixture frame {entry['file']}"
        grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        detected = {marker.marker_id: marker.corners for marker in detect_markers(grey)}
        frames.append((detected, entry["aim_point_screen_mm"]))

    return {
        "frames": frames,
        "layout_mm": layout_mm,
        "marker_size_mm": manifest["marker_size_mm"],
        "image_size": tuple(manifest["image_size"]),
    }


def _solve_subset(fixture_data: dict, detected: dict, marker_ids):
    """Solve using only the requested markers, or None if too few are visible."""
    available = [marker_id for marker_id in marker_ids if marker_id in detected]
    if not available:
        return None

    correspondences = []
    for marker_id in available:
        known_corners_mm = _marker_corners_mm(
            fixture_data["layout_mm"][marker_id], fixture_data["marker_size_mm"]
        )
        for screen_point, image_point in zip(
            known_corners_mm, detected[marker_id], strict=True
        ):
            correspondences.append(
                (screen_point, (float(image_point[0]), float(image_point[1])))
            )
    return solve(correspondences, fixture_data["image_size"])


def _error_mm(result, ground_truth) -> float:
    return float(
        np.hypot(
            result.aim_point_mm[0] - ground_truth[0],
            result.aim_point_mm[1] - ground_truth[1],
        )
    )


def test_a_well_spread_subset_stays_accurate(fixture_data: dict):
    """Half the layout, spread around the aim point, is nearly as good."""
    checked = 0
    for detected, ground_truth in fixture_data["frames"]:
        result = _solve_subset(fixture_data, detected, CORNERS)
        if result is None or len(set(CORNERS) & set(detected)) < len(CORNERS):
            continue
        checked += 1
        assert result.aim_point_inside_hull
        assert _error_mm(result, ground_truth) < WELL_CONDITIONED_TOLERANCE_MM
    assert checked > 0, "fixture never showed all four corners at once"


def test_markers_clustered_on_one_edge_are_flagged(fixture_data: dict):
    """Three markers, but all on the top bezel: the aim point is below
    them, so it is extrapolated off a near-degenerate baseline."""
    checked = 0
    for detected, _ in fixture_data["frames"]:
        result = _solve_subset(fixture_data, detected, TOP_EDGE)
        if result is None:
            continue
        checked += 1
        assert not result.aim_point_inside_hull
        assert result.aim_point_hull_distance_mm < 0.0
    assert checked > 0


def test_a_subset_spanning_only_one_axis_is_flagged(fixture_data: dict):
    """The left and right midpoints span the panel horizontally, but
    their hull is a thin horizontal band -- so an aim point above or
    below that band is still extrapolated, in one axis. The flag catches
    that even though the horizontal geometry looks generous."""
    flagged = 0
    checked = 0
    for detected, _ in fixture_data["frames"]:
        result = _solve_subset(fixture_data, detected, OPPOSITE_MIDPOINTS)
        if result is None or len(set(OPPOSITE_MIDPOINTS) & set(detected)) < 2:
            continue
        checked += 1
        flagged += not result.aim_point_inside_hull
    assert checked > 0
    assert flagged > 0


def test_a_single_marker_still_returns_an_answer_but_is_flagged(fixture_data: dict):
    """The solver must not refuse on conditioning grounds -- deciding
    what to do with a low-confidence aim point is the consumer's job."""
    checked = 0
    for detected, _ in fixture_data["frames"]:
        for marker_id in sorted(detected):
            result = _solve_subset(fixture_data, detected, (marker_id,))
            assert result is not None
            checked += 1
            assert not result.aim_point_inside_hull
    assert checked > 0


def test_single_marker_accuracy_is_still_poor(fixture_data: dict):
    """Documented observation, not a desired property.

    Extrapolating from one 80mm marker is measured at up to ~2m of error
    on a 1220mm panel. If a future pose-based solve (solvePnP with
    calibrated intrinsics) fixes this, this test fails and should be
    deleted along with the caveat it documents -- rather than the
    improvement landing silently.
    """
    worst = 0.0
    for detected, ground_truth in fixture_data["frames"]:
        for marker_id in sorted(detected):
            result = _solve_subset(fixture_data, detected, (marker_id,))
            worst = max(worst, _error_mm(result, ground_truth))
    assert worst > SPARSE_ERROR_IS_STILL_BAD_MM, (
        f"single-marker error peaked at {worst:.1f}mm, better than the "
        "documented behaviour -- did sparse solving improve? Revisit this "
        "test and README's accuracy caveats."
    )


def test_too_few_correspondences_cannot_be_solved(fixture_data: dict):
    """No markers in frame is a 'cannot solve', distinct from 'solved but
    poorly conditioned'. It must raise, not return a guess."""
    with pytest.raises(InsufficientCorrespondencesError):
        solve([], fixture_data["image_size"])

    detected, _ = fixture_data["frames"][0]
    one_marker = detected[sorted(detected)[0]]
    three_points = [
        ((0.0, 0.0), (float(one_marker[i][0]), float(one_marker[i][1])))
        for i in range(3)
    ]
    with pytest.raises(InsufficientCorrespondencesError):
        solve(three_points, fixture_data["image_size"])


def test_inside_hull_solves_are_bounded_across_every_subset(fixture_data: dict):
    """The headline property the conditioning flag buys.

    Sweeps every subset of the visible markers on every frame. Solves
    whose aim point is enclosed by their correspondences stay within a
    bounded error; the flag is therefore a usable filter, which
    reprojection error is not.
    """
    inside_errors = []
    outside_errors = []
    for detected, ground_truth in fixture_data["frames"]:
        available = sorted(detected)
        for count in range(1, len(available) + 1):
            for combo in itertools.combinations(available, count):
                result = _solve_subset(fixture_data, detected, combo)
                error = _error_mm(result, ground_truth)
                if result.aim_point_inside_hull:
                    inside_errors.append(error)
                else:
                    outside_errors.append(error)

    assert inside_errors and outside_errors
    assert max(inside_errors) < INSIDE_HULL_BOUND_MM, (
        f"an inside-hull solve was {max(inside_errors):.1f}mm off, past the "
        f"{INSIDE_HULL_BOUND_MM}mm bound this signal is supposed to give"
    )
    # The separation is the point: flagged solves are not merely
    # slightly worse, they are unbounded.
    assert max(outside_errors) > 10 * max(inside_errors)
