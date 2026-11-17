"""Each interface yields both sides of a fit from one definition, so the gap
between them is the configured clearance, and moves with it."""

import pytest

from boresight_case.geom import X, Y, Z, box, cylinder
from boresight_case.interfaces import (
    SKIN_T,
    AttachmentPoint,
    Fit,
    ModuleJoint,
    Peg,
    SlideFit,
)
from boresight_case.mesh import intersection_volume, min_gap, to_manifold
from boresight_case.vendor import M3_NUT_AF, M3_NUT_H, VENDOR

CLEARANCES = (0.15, 0.25, 0.35)


def joint() -> ModuleJoint:
    return ModuleJoint(
        name="test",
        mouth=(0, 0, 0),
        axis=(-1, 0, 0),
        u=Y,
        opening=(31.0, 45.0),
        depth=12.0,
        screw_dir=Y,
        screw_at=6.0,
        screw_offset=-10.0,
    )


def host_tube() -> object:
    # A receiver-like tube, its inside the joint's opening, running -x.
    outer = box(-40, 0, -18, 18, -25, 25)
    inner = box(-41, 1, -15.5, 15.5, -22.5, 22.5)
    return outer - inner


def joint_gap(fit: Fit) -> float:
    j = joint()
    host = host_tube() - j.host_cuts(fit, X)
    # The tenon inside the socket; its root collar seats on the socket's
    # end face, which is the shoulder that stops it.
    tenon = (j.tenon(fit, X) - j.tenon_cuts(fit, X)) & box(-40, -0.05, -30, 30, -30, 30)
    return min_gap(to_manifold(host), to_manifold(tenon))


@pytest.mark.parametrize("c", CLEARANCES)
def test_tenon_clears_its_socket_by_the_clearance(c):
    assert joint_gap(Fit(clearance=c)) == pytest.approx(c, abs=0.01)


def test_tenon_tracks_the_clearance():
    a = joint_gap(Fit(clearance=0.25))
    b = joint_gap(Fit(clearance=0.35))
    assert b - a == pytest.approx(0.1, abs=0.01)


def test_joint_screw_and_nut_line_up_and_clear_the_holes():
    fit = Fit()
    j = joint()
    host = to_manifold(host_tube() - j.host_cuts(fit, X))
    tenon = to_manifold(j.tenon(fit, X) - j.tenon_cuts(fit, X))
    screw = to_manifold(j.screw_location(fit) * VENDOR["m3x12"].build())
    nut = to_manifold(j.nut_location(fit, X) * VENDOR["m3-nut"].build())
    assert intersection_volume(screw, host) < 0.5
    assert intersection_volume(screw, tenon) < 0.5
    # The nut is a press fit: it overlaps the pocket walls by a sliver, the
    # interference times the nut's flanks.
    sliver = 6 * (M3_NUT_AF / 3**0.5) * M3_NUT_H * fit.interference
    assert intersection_volume(nut, tenon) == pytest.approx(sliver, rel=0.15)
    assert min_gap(screw, nut) < 0.05  # through the nut's hole


def test_insert_fastener_puts_the_insert_where_the_nut_was():
    fit = Fit(fastener="insert")
    j = joint()
    tenon = to_manifold(j.tenon(fit, X) - j.tenon_cuts(fit, X))
    insert = to_manifold(j.insert_location(fit) * VENDOR["m3-insert"].build())
    # The hole is smaller than the insert's knurl, which melts in.
    assert 0 < intersection_volume(insert, tenon) < 40


def attachment() -> AttachmentPoint:
    return AttachmentPoint(
        name="test", normal=Y, screw=(0, 18, 0), hook=(60, 18, 0), slide=X
    )


def core_wall(fit: Fit, a: AttachmentPoint) -> object:
    wall = box(-20, 80, 15.5, 18, -20, 20) + a.core_boss(X)
    return wall - a.core_cuts(fit, X)


def stem_gap(fit: Fit) -> float:
    a = attachment()
    # The stem where it passes through the wall, away from the flank face
    # the skin rests on.
    stem = a.hook_tab() & box(40, 80, 15.55, 17.95, -20, 20)
    return min_gap(to_manifold(core_wall(fit, a)), to_manifold(stem))


@pytest.mark.parametrize("c", CLEARANCES)
def test_hook_stem_clears_its_slot_by_the_clearance(c):
    assert stem_gap(Fit(clearance=c)) == pytest.approx(c, abs=0.01)


def test_hook_tracks_the_clearance():
    assert stem_gap(Fit(clearance=0.35)) - stem_gap(Fit(clearance=0.25)) == (
        pytest.approx(0.1, abs=0.01)
    )


def test_engaged_skin_rests_on_the_flank_without_overlap():
    fit = Fit()
    a = attachment()
    skin = box(-20, 80, 18, 18 + SKIN_T, -20, 20) + a.hook_tab() - a.skin_cuts(fit)
    wall = to_manifold(core_wall(fit, a))
    assert intersection_volume(to_manifold(skin), wall) < 0.01
    screw = to_manifold(a.screw_location() * VENDOR["m3x8"].build())
    assert intersection_volume(screw, to_manifold(skin)) < 0.5
    assert intersection_volume(screw, wall) < 0.5


def test_hook_wedge_passes_the_slot_before_sliding_home():
    fit = Fit()
    a = attachment()
    wall = to_manifold(core_wall(fit, a))
    # Offered to the slot short of home by the wedge and the clearance, the
    # whole hook goes straight in.
    tab = a.hook_tab().moved(_shift(-(1.6 + fit.clearance)))
    assert intersection_volume(to_manifold(tab), wall) < 0.01


def _shift(dx: float):
    from build123d import Location

    return Location((dx, 0, 0))


def peg_gap(fit: Fit) -> float:
    p = Peg(base=(0, 0, 0), axis=Z, hole_d=2.75, length=4.0, standoff_h=3.0)
    board = box(-5, 5, -5, 5, 3, 4.4) - p.hole()
    # The board rests on the standoff; the fit is between peg and hole.
    tip = p.peg(fit) & box(-5, 5, -5, 5, 3.05, 10)
    return min_gap(to_manifold(board), to_manifold(tip))


@pytest.mark.parametrize("c", CLEARANCES)
def test_peg_clears_its_hole_by_the_clearance(c):
    assert peg_gap(Fit(clearance=c)) == pytest.approx(c, abs=0.02)


def slide() -> SlideFit:
    return SlideFit(
        centre=(0, 0, 0), axis=Z, u=X, size=(30.0, 20.0), length=40.0, key=(6.0, 2.0)
    )


def slide_gap(fit: Fit) -> float:
    s = slide()
    host = box(-20, 20, -15, 15, 0, 40) - s.pocket()
    return min_gap(to_manifold(host), to_manifold(s.slider(fit)))


@pytest.mark.parametrize("c", CLEARANCES)
def test_slider_clears_its_pocket_and_key_by_the_clearance(c):
    assert slide_gap(Fit(clearance=c)) == pytest.approx(c, abs=0.01)


def test_slider_tracks_the_clearance():
    assert slide_gap(Fit(clearance=0.35)) - slide_gap(Fit(clearance=0.25)) == (
        pytest.approx(0.1, abs=0.01)
    )


def test_keyed_slider_does_not_go_in_reversed():
    fit = Fit()
    s = slide()
    host = to_manifold(box(-20, 20, -15, 15, 0, 40) - s.pocket())
    assert intersection_volume(to_manifold(s.slider(fit)), host) < 0.01
    assert intersection_volume(to_manifold(s.reversed_slider(fit)), host) > 50


def test_nut_pockets_are_a_press_fit_set_by_the_interference():
    assert Fit(interference=0.05).nut_af == pytest.approx(M3_NUT_AF - 0.1)
    assert Fit(interference=0.15).nut_af == pytest.approx(M3_NUT_AF - 0.3)


def test_teardrop_hole_admits_its_screw():
    from boresight_case.geom import teardrop

    hole = to_manifold(teardrop((0, -5, 0), Y, 1.7, 10, Z))
    shank = to_manifold(cylinder((0, -5, 0), Y, 1.5, 10))
    assert intersection_volume(shank, hole) == pytest.approx(shank.volume(), rel=0.01)
