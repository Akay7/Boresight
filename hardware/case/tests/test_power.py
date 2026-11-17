"""The power drawers, contacts and the Pi's cable (tasks 8.1, 8.2)."""

import pytest
from conftest import ESP32_DRAWERS, PI_CAMERAS, assembly, meshes, oriented

from boresight_case import checks
from boresight_case import layout as L
from boresight_case.assembly import pi_cable_path
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
def test_latched_drawer_sits_in_the_bay(cfg):
    m = meshes(cfg)
    assert intersection_volume(m[f"drawer-{cfg.power}"], m["grip"]) < 1.0


@pytest.mark.parametrize("cfg", ESP32_DRAWERS, ids=lambda c: c.power)
def test_reversed_drawer_does_not_go_in(cfg):
    """Turned the wrong way round, the drawer hits the key rib as soon as it
    enters the bay, long before its plates reach the springs."""
    from build123d import Axis, Location

    fit = Fit()
    shape = assembly(cfg).printed[f"drawer-{cfg.power}"].shape
    axis = Axis(L.grip_point(0), L.GRIP_D)
    reversed_ = shape.rotate(axis, 180)
    grip_mesh = meshes(cfg)["grip"]
    # Pushed only 10 mm into the bay:
    depth = L.GRIP_LENGTH - drawers.TOP_S - 10.0
    entering = Location(tuple(L.GRIP_D * depth)) * reversed_
    assert intersection_volume(to_manifold(entering), grip_mesh) > 20.0
    assert BAY_SLIDE.key is not None and fit.clearance > 0


@pytest.mark.parametrize("cfg", ESP32_DRAWERS, ids=lambda c: c.power)
def test_springs_meet_the_drawer_contacts(cfg):
    m = meshes(cfg)
    for sign in "+-":
        gap = m[f"spring contact {sign}"].min_gap(m[f"flat contact {sign}"], 2.0)
        assert gap < 0.05


def test_latch_release_is_in_the_drawer_zone():
    """The tongue's free end, pressed from below, is in a zone no skin may
    cover."""
    zone = to_manifold(zones()["drawer and latch"])
    (s0, s1), (y0, y1) = drawers.LATCH_NOTCH
    tab = to_manifold(
        drawers.grip_box(
            drawers.TONGUE_A, L.BAY_DEPTH / 2, y0, y1, L.GRIP_LENGTH, L.GRIP_LENGTH + 3
        )
    )
    assert intersection_volume(tab, zone) == pytest.approx(tab.volume(), rel=0.01)


def test_charge_port_and_indicator_are_in_keep_outs():
    port = to_manifold(drawers._charger_cuts(Fit()))
    below = to_manifold(
        drawers.grip_box(-30, 30, -30, 30, L.GRIP_LENGTH, L.GRIP_LENGTH + 5)
    )
    port_outside = port ^ below
    zone = to_manifold(zones()["drawer and latch"])
    assert (port_outside - zone).volume() < 0.1
    window = to_manifold(_charge_window())
    grip_mesh = to_manifold(grip(Fit()).printed[0].shape)
    indicator = to_manifold(zones()["charge indicator"])
    # The window is cut through the front wall; outside it, the zone.
    assert intersection_volume(window, grip_mesh) < 0.1
    assert indicator.min_gap(window, 1.0) < 0.1


def test_18650_charger_fits():
    cfg = Config(power="18650")
    m = meshes(cfg)
    assert intersection_volume(m["charger"], m["grip"]) < 1.0


@pytest.mark.parametrize("cfg", PI_CAMERAS, ids=lambda c: c.camera)
def test_pi_cable_runs_unbroken_from_plug_to_grip_base(cfg):
    path = pi_cable_path()
    plug = assembly(cfg).bought_by_label()["USB plug"].shape.bounding_box()
    start = path[0]
    assert plug.min.X - 0.5 <= start[0] <= plug.max.X + 0.5
    end = path[-1]
    rel = [e - t for e, t in zip(end, L.GRIP_TOP, strict=True)]
    s = sum(r * d for r, d in zip(rel, L.GRIP_D, strict=True))
    assert s > L.GRIP_LENGTH  # it leaves through the base
    m = meshes(cfg)
    printed = {n: mm for n, mm in m.items() if n in assembly(cfg).printed}
    assert checks.overlapping(m["usb cable"], printed, "cable", "usb cable") == []


def test_pi_kit_has_no_battery_path():
    labels = {b.label for b in assembly(PI_CAMERAS[0]).bought}
    assert not labels & {"power switch", "regulator", "spring contact +", "cell holder"}
    assert "status LED" in labels


def test_esp32_kit_has_a_switch_and_regulator_on_every_drawer():
    for cfg in ESP32_DRAWERS:
        labels = {b.label for b in assembly(cfg).bought}
        assert {
            "power switch",
            "regulator",
            "spring contact +",
            "spring contact -",
        } <= labels
