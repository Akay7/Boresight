"""The hub and the wiring (tasks 8.1 to 8.3)."""

import pytest
from conftest import assembly, lead_meshes, meshes

from boresight_case import checks, wiring
from boresight_case import layout as L
from boresight_case.config import Config, shipped_configurations
from boresight_case.keepouts import zones
from boresight_case.mesh import intersection_volume, to_manifold
from boresight_case.parts import carriers

ALL = shipped_configurations()


def test_the_hub_sits_on_the_receivers_left_rails_above_the_grip():
    hub = assembly(Config()).printed["hub"].shape.bounding_box()
    assert hub.min.X == pytest.approx(L.HUB_X[0], abs=0.01)
    assert hub.min.X < L.GRIP_TOP.X < hub.max.X


def test_the_hub_holds_every_part_the_spec_names():
    labels = {b.label for b in assembly(Config()).bought if b.module == "hub"}
    assert {
        "regulator",
        "ideal diode",
        "power switch",
        "power LED",
        "status LED",
        "5 V and GND test pins",
        "solenoid fuse",
    } <= labels
    for s in carriers.SOCKETS:
        assert f"{s.lead} socket" in labels


def test_the_switch_knob_and_leds_come_out_where_the_covers_keep_out():
    """The knob passes the receiver's slot to the left wall's outside, and
    it and the LEDs sit in the covers' keep-out opening."""
    a = assembly(Config())
    m = meshes(Config())
    zone = to_manifold(zones()["switch, LEDs and buttons"])
    knob = a.bought_by_label()["power switch"].shape.bounding_box()
    assert knob.max.Y > L.HALF_W
    for part in ("power switch", "power LED", "status LED"):
        assert intersection_volume(m[part], m["receiver"]) < 0.5, part
        near = m[part].min_gap(zone, 3.0)
        assert near < 1.0, part


@pytest.mark.parametrize("cfg", ALL, ids=lambda c: c.name)
def test_short_leads_are_at_most_60_mm(cfg):
    for lead in wiring.leads(cfg):
        if lead.name in wiring.SHORT_LEADS:
            assert lead.length <= wiring.SHORT_MAX, (lead.name, lead.length)


@pytest.mark.parametrize("cfg", ALL, ids=lambda c: c.name)
def test_every_module_has_exactly_one_lead_to_the_hub(cfg):
    to_hub = [lead for lead in wiring.leads(cfg) if lead.to.startswith("hub ")]
    modules = [lead.module for lead in to_hub]
    # One lead each; the Pi's sled has its power lead beside its signal lead.
    assert len(modules) - (cfg.board == "pi-zero-2w") == len(set(modules))
    expected = {"grip", "trigger", "nose" if cfg.board == "esp32-cam" else "sled"}
    if cfg.feedback != "none":
        expected.add(f"feedback ({cfg.feedback})")
    if cfg.buttons:
        expected.add("buttons")
    assert set(modules) == expected
    sockets = [lead.to for lead in to_hub]
    assert len(sockets) == len(set(sockets))  # one socket each


def test_a_pi_on_a_host_cable_powers_the_hub_through_the_ideal_diode():
    """The Pi's power lead and the regulator meet at the ideal diode, so a
    Pi on a host cable runs the hub without back-feeding the regulator."""
    labels = {b.label for b in assembly(Config(board="pi-zero-2w", power="usb")).bought}
    assert {"ideal diode", "regulator", "pi power socket", "power plug"} <= labels


def test_the_leads_clear_every_printed_part_they_pass():
    for cfg in (
        Config(),
        Config(board="pi-zero-2w"),
        Config(barrels=2),
        Config(barrels=0),
    ):
        a = assembly(cfg)
        m = meshes(cfg)
        printed = {n: mm for n, mm in m.items() if n in a.printed}
        for name, lead in lead_meshes(cfg).items():
            hits = checks.overlapping(lead, printed, "lead", name, tolerance=1.0)
            assert hits == [], (cfg.name, [h.text() for h in hits])
