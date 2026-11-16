"""The trigger: its three mechanisms and the switch plates they share
(tasks 6.1, 6.2, 12.2, 12.3)."""

import math

import pytest
from conftest import MECHANISM_CONFIGS, assembly, meshes, oriented

from boresight_case import catalog, checks
from boresight_case import layout as L
from boresight_case.config import Config
from boresight_case.geom import cylinder
from boresight_case.interfaces import Fit
from boresight_case.joints import CASSETTE_SCREW
from boresight_case.mesh import intersection_volume, to_manifold
from boresight_case.parts import button as B
from boresight_case.parts import trigger as T
from boresight_case.vendor import M3_HEAD_H, MX_STEM_TOP

LEVERS = [c for c in MECHANISM_CONFIGS if c.mechanism != "button"]
BUTTONS = [c for c in MECHANISM_CONFIGS if c.mechanism == "button"]


def _id(c: Config) -> str:
    return f"{c.mechanism}-{c.trigger}"


def _printed(cfg):
    a = assembly(cfg)
    return {n: mm for n, mm in meshes(cfg).items() if n in a.printed}


@pytest.mark.parametrize("cfg", MECHANISM_CONFIGS, ids=_id)
def test_mechanism_parts_print_without_support_and_fit_the_bed(cfg):
    names = (*catalog.MECHANISM_PARTS[cfg.mechanism], f"switch-plate-{cfg.trigger}")
    for name in names:
        part = oriented(cfg, name)
        assert checks.overhangs(name, part) == [], name
        assert checks.bed_fit(name, part, cfg.printer.volume) == [], name


@pytest.mark.parametrize("cfg", MECHANISM_CONFIGS, ids=_id)
def test_cassette_fits_the_receiver_with_one_screw(cfg):
    a = assembly(cfg)
    m = meshes(cfg)
    body = catalog.MECHANISM_PARTS[cfg.mechanism][0]
    assert intersection_volume(m[body], m["receiver"]) < 1.0
    teardown = [b for b in a.bought if b.module == "trigger-cassette" and b.teardown]
    assert [b.label for b in teardown] == ["cassette screw"]


@pytest.mark.parametrize("cfg", MECHANISM_CONFIGS, ids=_id)
def test_cassette_screw_stays_reachable_from_below(cfg):
    """A hex key goes straight up to the cassette screw's head, past every
    printed part."""
    entry = CASSETTE_SCREW.entry
    key = to_manifold(
        cylinder((entry[0], entry[1], entry[2] - 0.5), (0, 0, -1), 1.4, 60)
    )
    assert checks.overlapping(key, _printed(cfg), "hex key", "cassette screw") == []


def test_every_mechanism_shares_the_plates_switch_and_lead():
    for trigger in ("mx", "microswitch"):
        keys = {}
        for mechanism in ("filament", "bolt", "button"):
            a = assembly(Config(mechanism=mechanism, trigger=trigger))
            plate = a.printed[f"switch-plate-{trigger}"].shape
            labels = a.bought_by_label()
            keys[mechanism] = (
                round(plate.volume, 3),
                labels["trigger switch"].key,
                labels["trigger plug"].key,
            )
        assert len(set(keys.values())) == 1, keys


# -- the levers (filament pin and bolt) -----------------------------------------------


@pytest.mark.parametrize("cfg", LEVERS, ids=_id)
def test_lever_sweep_clears_every_printed_part(cfg):
    """From rest to the stop, the lever touches nothing printed: only the
    switch, which it presses, and the spring."""
    lever = catalog.MECHANISM_PARTS[cfg.mechanism][1]
    sweep = to_manifold(T.lever_sweep(cfg.trigger, mechanism=cfg.mechanism))
    others = {n: mm for n, mm in _printed(cfg).items() if n != lever}
    assert checks.overlapping(sweep, others, "lever travel", "lever") == []


@pytest.mark.parametrize("trigger", ("mx", "microswitch"))
def test_lever_default_stop_is_past_actuation_and_short_of_end_of_travel(trigger):
    actuate, end = T.switch_limits(trigger)
    stop = T.pad_travel(T.angle_for_travel(L.STOP_TRAVEL[trigger]))
    assert actuate < stop < end
    if trigger == "mx":
        assert 2.0 < stop < 4.0


@pytest.mark.parametrize("trigger", ("mx", "microswitch"))
def test_lever_at_rest_does_not_actuate_the_switch(trigger):
    actuate, _ = T.switch_limits(trigger)
    assert T.pad_travel(0.0) == pytest.approx(0.0)
    assert T.pad_travel(0.0) < actuate


def test_mx_stem_just_touches_the_contact_line_at_rest():
    assert T.MX_FACE_X + MX_STEM_TOP == pytest.approx(T.CONTACT_X)


@pytest.mark.parametrize("cfg", LEVERS, ids=_id)
def test_stop_screw_meets_the_upper_arm_at_the_stop(cfg):
    """Just short of the stop angle the lever clears the screw; just past
    it, the lever runs into it."""
    screw = meshes(cfg)["stop screw"]
    stop = T.angle_for_travel(L.STOP_TRAVEL[cfg.trigger])
    before = to_manifold(T.lever_shape(stop - math.radians(0.5), cfg.mechanism))
    after = to_manifold(T.lever_shape(stop + math.radians(1.5), cfg.mechanism))
    assert intersection_volume(before, screw) < 0.05
    assert intersection_volume(after, screw) > 0.3


@pytest.mark.parametrize("trigger", ("mx", "microswitch"))
def test_pivot_bolt_runs_through_the_lever_into_its_nut(trigger):
    """The M3 x 12 spans the lever and both bosses: its head and nut are
    sunk into the bosses, it clears the lever's hub and the cassette, and
    it reaches through the nut."""
    m = meshes(Config(mechanism="bolt", trigger=trigger))
    bolt, nut = m["pivot bolt"], m["nut, pivot bolt"]
    assert intersection_volume(bolt, m["trigger-lever-bolt"]) < 0.05
    assert intersection_volume(bolt, m["trigger-cassette-bolt"]) < 0.05
    assert bolt.min_gap(nut, 1.0) < 0.05
    lo, hi = bolt.bounding_box()[1], bolt.bounding_box()[4]
    w = L.CASSETTE_HALF_W
    assert -w < lo and hi < w  # nothing proud of the cassette's flanks
    nut_lo = nut.bounding_box()[1]
    assert lo < nut_lo  # the bolt's tip is past the nut


def test_filament_and_bolt_levers_differ_only_in_their_bore():
    pin = T.lever_shape(0.0, "filament")
    bolt = T.lever_shape(0.0, "bolt")
    bore = math.pi * L.LEVER_W * ((T.M3_CLEAR / 2) ** 2 - (T.PIN_D / 2 + 0.1) ** 2)
    assert pin.volume - bolt.volume == pytest.approx(bore, rel=0.02)


# -- the push button ------------------------------------------------------------------


@pytest.mark.parametrize("cfg", BUTTONS, ids=_id)
def test_button_travel_clears_every_printed_part(cfg):
    sweep = to_manifold(B.button_sweep(cfg.trigger))
    others = {
        n: mm
        for n, mm in _printed(cfg).items()
        if n not in ("button-plunger", "button-cap")
    }
    assert checks.overlapping(sweep, others, "button travel", "button") == []


@pytest.mark.parametrize("cfg", BUTTONS, ids=_id)
def test_button_stops_past_actuation_and_short_of_end_of_travel(cfg):
    """The cap meets the stop screw's head after the plate's default
    travel, which lies between the switch's actuation and its end."""
    m = meshes(cfg)
    gap = m["button-cap"].min_gap(m["stop screw"], 10.0)
    actuate, end = T.switch_limits(cfg.trigger)
    assert gap == pytest.approx(L.STOP_TRAVEL[cfg.trigger], abs=0.05)
    assert actuate < gap < end


@pytest.mark.parametrize("cfg", BUTTONS, ids=_id)
def test_button_meets_the_switch_on_the_contact_line(cfg):
    """At rest the plunger's head is on the same line the lever's pad was,
    so the button moves as far as the switch does."""
    plunger = assembly(cfg).printed["button-plunger"].shape.bounding_box()
    assert plunger.min.X == pytest.approx(T.CONTACT_X)
    switch = meshes(cfg)["trigger switch"]
    assert meshes(cfg)["button-plunger"].min_gap(switch, 1.0) < 0.05


def test_button_stop_head_clears_the_cap_at_rest():
    for trigger in ("mx", "microswitch"):
        gap = B.stroke_gap(L.STOP_TRAVEL[trigger])
        assert 0 < gap < B.CAP_X[0] - B.FRONT - M3_HEAD_H


def test_switch_plates_share_the_seat():
    """Both plates have the same outline where they slide into the
    cassette, so either fits every mechanism."""
    from boresight_case.geom import box

    fit = Fit()
    seat = T._plate_outline(fit).bounding_box()
    # Within the seat's thickness, where the plate rides in the grooves.
    slab = box(L.PLATE_X[0], L.PLATE_X[1] - 0.05, -20, 20, -80, 0)
    for plate in (T.mx_plate(fit), T.micro_carrier(fit)):
        bb = (plate & slab).bounding_box()
        assert bb.min.Y == pytest.approx(seat.min.Y)
        assert bb.max.Y == pytest.approx(seat.max.Y)
        assert bb.min.Z >= seat.min.Z - 1e-6 and bb.max.Z <= seat.max.Z + 1e-6
