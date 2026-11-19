"""The power drawers and their thumbscrew (task 7.1)."""

import pytest
from conftest import ESP32_DRAWERS, assembly, meshes, oriented

from boresight_case import checks
from boresight_case import layout as L
from boresight_case.config import Config
from boresight_case.interfaces import Fit
from boresight_case.joints import BAY_SLIDE
from boresight_case.keepouts import zones
from boresight_case.mesh import intersection_volume, to_manifold
from boresight_case.parts import drawers
from boresight_case.parts.grip import _charge_window, grip


@pytest.mark.parametrize("cfg", ESP32_DRAWERS, ids=lambda c: c.power)
def test_drawer_prints_without_support(cfg):
    name = f"drawer-{cfg.power}"
    assert checks.overhangs(name, oriented(cfg, name)) == []
    assert checks.bed_fit(name, oriented(cfg, name), cfg.printer.volume) == []


@pytest.mark.parametrize("cfg", ESP32_DRAWERS, ids=lambda c: c.power)
def test_a_drawer_pushed_home_sits_in_the_bay(cfg):
    m = meshes(cfg)
    assert intersection_volume(m[f"drawer-{cfg.power}"], m["grip"]) < 1.0


@pytest.mark.parametrize("cfg", ESP32_DRAWERS, ids=lambda c: c.power)
def test_a_reversed_drawer_does_not_go_in(cfg):
    """Turned the wrong way round, the drawer hits the key rib as soon as it
    enters the bay, long before its plates reach the springs."""
    from build123d import Axis, Location

    shape = assembly(cfg).printed[f"drawer-{cfg.power}"].shape
    reversed_ = shape.rotate(Axis(L.grip_point(0), L.GRIP_D), 180)
    depth = L.GRIP_LENGTH - drawers.TOP_S - 10.0
    entering = Location(tuple(L.GRIP_D * depth)) * reversed_
    assert intersection_volume(to_manifold(entering), meshes(cfg)["grip"]) > 20.0
    assert BAY_SLIDE.key is not None


@pytest.mark.parametrize("cfg", ESP32_DRAWERS, ids=lambda c: c.power)
def test_springs_meet_the_drawer_contacts(cfg):
    m = meshes(cfg)
    for sign in "+-":
        gap = m[f"spring contact {sign}"].min_gap(m[f"flat contact {sign}"], 2.0)
        assert gap < 0.05


@pytest.mark.parametrize("cfg", ESP32_DRAWERS, ids=lambda c: c.power)
def test_the_thumbscrew_locks_the_drawer_clear_of_the_contacts(cfg):
    """It turns through the drawer's foot into the nut in the grip's front
    boss, well away from the contacts in the bay."""
    m = meshes(cfg)
    screw, nut = m["thumbscrew"], m["nut, thumbscrew"]
    assert screw.min_gap(nut, 1.0) < 0.05
    assert intersection_volume(screw, m["grip"]) < 0.5
    assert intersection_volume(screw, m[f"drawer-{cfg.power}"]) < 0.5
    for sign in "+-":
        assert screw.min_gap(m[f"spring contact {sign}"], 20.0) > 10.0


def test_no_printed_part_flexes_to_hold_the_drawer():
    """The drawers are PLA or PETG now: nothing in them bends."""
    for cfg in ESP32_DRAWERS:
        p = assembly(cfg).printed[f"drawer-{cfg.power}"]
        assert p.material == "PLA or PETG"


def test_the_charge_port_and_indicator_are_in_keep_outs():
    port = to_manifold(drawers._charger_cuts(Fit()))
    below = to_manifold(
        drawers.grip_box(-30, 30, -30, 30, L.GRIP_LENGTH, L.GRIP_LENGTH + 5)
    )
    port_outside = port ^ below
    zone = to_manifold(zones()["drawer and thumbscrew"])
    assert (port_outside - zone).volume() < 0.1
    window = to_manifold(_charge_window())
    grip_mesh = to_manifold(grip(Fit()).printed[0].shape)
    assert intersection_volume(window, grip_mesh) < 0.1
    assert to_manifold(zones()["charge indicator"]).min_gap(window, 1.0) < 0.1


def test_the_18650_charger_fits():
    m = meshes(Config(power="18650"))
    assert intersection_volume(m["charger"], m["grip"]) < 1.0
