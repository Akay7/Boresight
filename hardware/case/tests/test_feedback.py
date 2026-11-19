"""The feedback carriers and the Start and Select buttons (tasks 11.1, 11.2,
12.1)."""

import pytest
from conftest import FEEDBACK, assembly, meshes, oriented

from boresight_case import checks, wiring
from boresight_case import layout as L
from boresight_case.config import Config
from boresight_case.keepouts import zones
from boresight_case.mesh import intersection_volume, to_manifold
from boresight_case.vendor import PI_SIGNAL_PINS


@pytest.mark.parametrize("cfg", FEEDBACK, ids=lambda c: c.name)
def test_each_carrier_fits_with_each_board(cfg):
    a = assembly(cfg)
    assert checks.interference(meshes(cfg), a.press_fits) == []
    for p in a.printed.values():
        if p.module == "feedback":
            o = oriented(cfg, p.name)
            assert checks.overhangs(p.name, o) == [], p.name


@pytest.mark.parametrize("cfg", FEEDBACK, ids=lambda c: c.name)
def test_every_carrier_rides_the_same_rails_in_the_same_place(cfg):
    a = assembly(cfg)
    plate = next(p for p in a.printed.values() if p.part.startswith("feedback-"))
    bb = plate.shape.bounding_box()
    assert bb.min.X == pytest.approx(L.FEEDBACK_X[0], abs=0.01)
    assert bb.min.Y == pytest.approx(-L.IN_HALF_W + L.PLATE_OFF, abs=0.01)


def test_without_feedback_a_spacer_takes_the_carriers_place():
    a = assembly(Config())
    spacer = a.printed["spacer-40 right"].shape.bounding_box()
    assert spacer.min.X == pytest.approx(L.FEEDBACK_X[0], abs=0.01)
    assert not any(lead.name == "feedback lead" for lead in wiring.leads(Config()))


@pytest.mark.parametrize("cfg", FEEDBACK, ids=lambda c: c.name)
def test_the_feedback_lead_is_short(cfg):
    lead = next(x for x in wiring.leads(cfg) if x.name == "feedback lead")
    assert lead.length <= wiring.SHORT_MAX


@pytest.mark.parametrize("board", ("esp32-cam", "pi-zero-2w"))
def test_no_feedback_pin_is_a_trigger_led_or_button_pin(board):
    taken = {
        "esp32-cam": {"IO13", "IO33", "IO0", "U0R", "U0T"},
        "pi-zero-2w": {"GPIO17", "GPIO27", "GPIO4", "GPIO10"},
    }[board]
    for kind, pins in wiring.FEEDBACK_PINS[board].items():
        for pin in pins:
            for t in taken:
                assert t not in pin, (kind, pin)
    if board == "pi-zero-2w":
        assert PI_SIGNAL_PINS[15] == "GPIO22"
        assert PI_SIGNAL_PINS[3] == "SDA" and PI_SIGNAL_PINS[5] == "SCL"


def test_the_buttons_come_out_where_the_covers_keep_out():
    cfg = Config(board="pi-zero-2w", buttons=True)
    a = assembly(cfg)
    m = meshes(cfg)
    assert checks.interference(m, a.press_fits) == []
    zone = to_manifold(zones()["switch, LEDs and buttons"])
    for label in ("Start button", "Select button"):
        assert intersection_volume(m[label], m["receiver"]) < 0.5
        assert m[label].min_gap(zone, 3.0) < 0.5
    lead = next(x for x in wiring.leads(cfg) if x.name == "buttons lead")
    assert any("GPIO4" in p for p in lead.pins) and any(
        "GPIO10" in p for p in lead.pins
    )
