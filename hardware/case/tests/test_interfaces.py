"""Each interface yields both sides of a fit from one definition, so the gap
between them is the configured clearance, and moves with it."""

import pytest

from boresight_case.geom import X, Y, Z, box, cylinder
from boresight_case.interfaces import (
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


# -- the port and its through-bolts ---------------------------------------------------


def port_pair(fit: Fit):
    """A receiver-like host round the receiver's front port, and the
    standard tenon that fills it."""
    from boresight_case.geom import NEG_X
    from boresight_case.joints import RECEIVER_PORT

    host = box(-40, 0, -18, 18, -25, 25) - box(-41, 1, -15.5, 15.5, -22.5, 22.5)
    host = host + RECEIVER_PORT.rib() - RECEIVER_PORT.host_cuts(X)
    tenon = RECEIVER_PORT.tenon(fit, NEG_X)
    return host, tenon


@pytest.mark.parametrize("c", CLEARANCES)
def test_a_tenon_clears_its_port_by_the_clearance(c):
    host, tenon = port_pair(Fit(clearance=c))
    inside = tenon & box(-40, -0.05, -30, 30, -30, 30)
    assert min_gap(to_manifold(host), to_manifold(inside)) == pytest.approx(c, abs=0.01)


def test_an_upside_down_tenon_hits_the_key_rib():
    from build123d import Axis

    host, tenon = port_pair(Fit())
    flipped = tenon.rotate(Axis((0, 0, 0), (1, 0, 0)), 180)
    assert intersection_volume(to_manifold(host), to_manifold(tenon)) < 0.5
    assert intersection_volume(to_manifold(host), to_manifold(flipped)) > 20


def test_port_bolts_line_up_through_every_layer():
    """Each bolt passes the covers' flanges, the host's walls and the
    tenon's crush tube without touching any, on its washer and lock nut."""
    from boresight_case.interfaces import FLANGE
    from boresight_case.joints import RECEIVER_PORT

    fit = Fit()
    host, tenon = port_pair(fit)
    for b in RECEIVER_PORT.bolts:
        bolt = to_manifold(b.bolt_location() * VENDOR["m3x50"].build())
        assert intersection_volume(bolt, to_manifold(host)) < 0.5
        assert intersection_volume(bolt, to_manifold(tenon)) < 0.5
        # The clamp: the body, a flange each side and the lock nut.
        assert 2 * b.half + 2 * FLANGE + 4.0 == pytest.approx(46.0)
        nut = to_manifold(b.nut_location(X) * VENDOR["m3-nyloc"].build())
        assert bolt.min_gap(nut, 1.0) < 0.05  # through the nut
        tip = bolt.bounding_box()[1]
        assert tip < -(b.half + FLANGE + 4.0)  # past the nut


def test_the_crush_tube_fills_the_tenon_from_wall_to_wall():
    from boresight_case.joints import RECEIVER_PORT

    _, tenon = port_pair(Fit())
    for b in RECEIVER_PORT.bolts:
        x, _, z = b.centre
        ring = box(x - 3.2, x + 3.2, -12.0, 12.0, z - 3.2, z + 3.2) - cylinder(
            (x, -13, z), Y, 2.0, 26
        )
        filled = intersection_volume(to_manifold(ring), to_manifold(tenon))
        assert filled > 0.6 * to_manifold(ring).volume()


# -- rails and carriers ----------------------------------------------------------------


@pytest.mark.parametrize("side", (1, -1))
@pytest.mark.parametrize("c", CLEARANCES)
def test_a_carrier_slides_in_its_rails_by_the_clearance(side, c):
    from boresight_case.interfaces import carrier_plate, rails

    fit = Fit(clearance=c)
    channel = rails(-80, -20, side, fit, X)
    plate = carrier_plate(-80, -20, side)
    assert min_gap(to_manifold(channel), to_manifold(plate)) == pytest.approx(
        c, abs=0.01
    )
    # And it is held: it cannot come off the wall.
    from build123d import Location

    off = Location((0, -side * 1.5, 0)) * plate
    assert intersection_volume(to_manifold(channel), to_manifold(off)) > 1.0


def test_spacers_fill_each_run_to_within_the_clearance():
    from boresight_case import catalog
    from boresight_case import layout as L
    from boresight_case.config import Config

    fit = Fit()
    run = L.RECEIVER_RUN[1] - L.RECEIVER_RUN[0]
    hub = L.HUB_X[1] - L.HUB_X[0]
    for buttons in (False, True):
        left = hub + sum(n for n, _ in catalog.SPACER_LEFT[buttons])
        assert left == pytest.approx(run)
    right = sum(n for n, _ in catalog.SPACER_RIGHT) + catalog.NO_FEEDBACK[0]
    assert right == pytest.approx(run)
    assert L.FEEDBACK_X[1] - L.FEEDBACK_X[0] == catalog.NO_FEEDBACK[0]
    from conftest import assembly

    a = assembly(Config())
    ends = sorted(
        p.shape.bounding_box().max.X for p in a.printed.values() if p.module == "spacer"
    )
    assert L.RECEIVER_RUN[1] - ends[-1] == pytest.approx(fit.clearance, abs=0.01)


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
