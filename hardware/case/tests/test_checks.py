"""The geometry checks themselves, on solids whose answer is known."""

import math

import pytest
from build123d import Location

from boresight_case.checks import (
    analyse_overhangs,
    bed_fit,
    interference,
    overhangs,
    overlapping,
    too_close,
)
from boresight_case.geom import X, Y, Z, box, cylinder, prism, side_profile, teardrop
from boresight_case.mesh import to_manifold
from boresight_case.optics import view_frustum
from boresight_case.vendor import VENDOR

# -- bed fit -------------------------------------------------------------------


def test_part_that_fits_passes():
    part = to_manifold(box(0, 170, 0, 100, 0, 60))
    assert bed_fit("barrel", part, (180, 180, 180)) == []


def test_oversized_part_fails_naming_it_and_its_size():
    part = to_manifold(box(0, 200, 0, 100, 0, 60))
    (problem,) = bed_fit("receiver", part, (180, 180, 180))
    assert problem.parts == ("receiver",)
    assert "200.0 x 100.0 x 60.0" in problem.detail


def test_part_turned_a_quarter_turn_fits():
    part = to_manifold(box(0, 100, 0, 200, 0, 50))
    assert bed_fit("grip", part, (220, 120, 100)) == []


def test_too_tall_part_fails():
    part = to_manifold(box(0, 50, 0, 50, 0, 190))
    assert bed_fit("grip", part, (180, 180, 180))


# -- interference ----------------------------------------------------------------


def test_overlapping_boxes_fail_naming_both():
    parts = {
        "a": to_manifold(box(0, 10, 0, 10, 0, 10)),
        "b": to_manifold(box(8, 18, 0, 10, 0, 10)),
    }
    (problem,) = interference(parts)
    assert set(problem.parts) == {"a", "b"}
    assert "200.0" in problem.detail


def test_touching_boxes_pass():
    parts = {
        "a": to_manifold(box(0, 10, 0, 10, 0, 10)),
        "b": to_manifold(box(10, 20, 0, 10, 0, 10)),
    }
    assert interference(parts) == []


def test_a_declared_press_fit_passes():
    parts = {
        "nut": to_manifold(box(0, 10, 0, 10, 0, 10)),
        "boss": to_manifold(box(9.9, 20, 0, 10, 0, 10)),
    }
    assert interference(parts)
    assert interference(parts, allowed=[frozenset(("nut", "boss"))]) == []


def test_part_entering_a_zone_is_named():
    zone = to_manifold(box(0, 10, 0, 10, 0, 10))
    parts = {
        "in": to_manifold(box(5, 15, 0, 10, 0, 10)),
        "out": to_manifold(box(20, 30, 0, 10, 0, 10)),
    }
    (problem,) = overlapping(zone, parts, "keep-out", "vents")
    assert problem.parts == ("in", "vents")


# -- overhangs -----------------------------------------------------------------


def _wedge(angle_from_vertical: float, run: float = 20.0):
    """A block on the bed whose -x side leans out over the bed at the given
    angle from vertical, from 2 mm up: an overhang of that steepness."""
    rise = run / math.tan(math.radians(angle_from_vertical))
    pts = [(0, 0), (30, 0), (30, 2 + rise), (-run, 2 + rise), (0, 2)]
    return side_profile(pts, 0, 20)


def test_sixty_degree_overhang_fails_naming_the_part():
    part = to_manifold(_wedge(60))
    (problem,) = overhangs("lever", part)
    assert problem.check == "overhang" and problem.parts == ("lever",)


def test_forty_five_degree_chamfer_passes():
    assert overhangs("plate", to_manifold(_wedge(45))) == []


def test_vertical_walls_and_the_bed_face_pass():
    assert overhangs("block", to_manifold(box(0, 40, 0, 30, 0, 20))) == []


def _bridge(span: float):
    """Two posts joined at the top by a slab: the slab's underside bridges
    `span` mm between them, across a 30 mm wide slab."""
    left = box(0, 5, 0, 30, 0, 10)
    right = box(5 + span, 10 + span, 0, 30, 0, 10)
    top = box(0, 10 + span, 0, 30, 10, 12)
    return left + right + top


def test_ten_mm_bridge_passes():
    report = analyse_overhangs(to_manifold(_bridge(10)))
    assert report.steep_area == 0
    assert report.bridges == pytest.approx((10.0,))
    assert overhangs("arch", to_manifold(_bridge(10))) == []


def test_twelve_mm_bridge_fails():
    assert overhangs("arch", to_manifold(_bridge(12)))


def test_horizontal_teardrop_hole_passes():
    block = box(0, 20, 0, 20, 0, 20) - teardrop((10, -1, 10), Y, 1.7, 22, Z)
    assert overhangs("boss", to_manifold(block)) == []


def test_horizontal_round_hole_is_an_overhang():
    block = box(0, 20, 0, 20, 0, 20) - cylinder((10, -1, 10), Y, 4, 22)
    report = analyse_overhangs(to_manifold(block))
    assert report.steep_area > 0


# -- field of view and clearance ---------------------------------------------------


def frustum():
    return view_frustum("ov2640", (0, 0, 0), 60.0)


def test_frustum_opens_with_the_cameras_field_of_view():
    bb = frustum().bounding_box()
    hfov = VENDOR["ov2640"].dims["hfov"]
    half = (bb.max.Y - bb.min.Y) / 2
    # At 60 mm the half-width is the pupil plus the distance times the
    # tangent of half the FOV plus the margin.
    expected = 1.3 + 61 * math.tan(math.radians(hfov / 2 + 3))
    assert half == pytest.approx(expected, rel=0.01)
    assert bb.max.Z - bb.min.Z < bb.max.Y - bb.min.Y


def _ring(inner: float, at: float = 20.0):
    outer = cylinder((at, 0, 0), X, inner + 3, 2) - cylinder(
        (at - 1, 0, 0), X, inner, 4
    )
    return outer


def test_ring_inside_the_frustum_fails():
    zone = to_manifold(frustum())
    parts = {"shroud": to_manifold(_ring(8))}
    assert overlapping(zone, parts, "field of view", "ov2640")


def test_wider_ring_passes():
    zone = to_manifold(frustum())
    # At 22 mm the view is about 15 mm across half its width.
    parts = {"shroud": to_manifold(_ring(20))}
    assert overlapping(zone, parts, "field of view", "ov2640") == []


def test_nut_nine_mm_away_fails_the_ten_mm_rule():
    antenna = to_manifold(box(0, 4, -9, 9, 14, 20))
    # The nut's lower face 9 mm above the antenna's top (z=20); it is 2.4 tall.
    nut = to_manifold(Location((2, 0, 29 + 1.2)) * VENDOR["m3-nut"].build())
    (problem,) = too_close("antenna", antenna, {"nut": nut}, 10.0, "antenna")
    assert problem.parts == ("nut", "antenna")
    far = to_manifold(Location((2, 0, 31 + 1.2)) * VENDOR["m3-nut"].build())
    assert too_close("antenna", antenna, {"nut": far}, 10.0, "antenna") == []


def test_prism_helper_extrudes_along_its_normal():
    p = prism((0, 0, 0), X, Y, [(0, 0), (1, 0), (0, 1)], 3)
    assert p.bounding_box().max.Z == pytest.approx(3)
