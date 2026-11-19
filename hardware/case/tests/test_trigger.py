"""The trigger in the grip: its two mechanisms and the switch plates they
share (tasks 6.1, 6.2)."""

import math

import pytest
from conftest import MECHANISM_CONFIGS, assembly, meshes, oriented

from boresight_case import catalog, checks
from boresight_case import layout as L
from boresight_case.config import Config
from boresight_case.interfaces import Fit
from boresight_case.mesh import intersection_volume, to_manifold
from boresight_case.parts import button as B
from boresight_case.parts import trigger as T
from boresight_case.vendor import MX_STEM_TOP

LEVERS = [c for c in MECHANISM_CONFIGS if c.mechanism == "bolt"]
BUTTONS = [c for c in MECHANISM_CONFIGS if c.mechanism == "button"]


def _id(c: Config) -> str:
    return f"{c.mechanism}-{c.trigger}"


def _printed(cfg, skins=False):
    a = assembly(cfg, skins)
    return {n: mm for n, mm in meshes(cfg, skins).items() if n in a.printed}


@pytest.mark.parametrize("cfg", MECHANISM_CONFIGS, ids=_id)
def test_trigger_parts_print_without_support_and_fit_the_bed(cfg):
    names = (*catalog.MECHANISM_PARTS[cfg.mechanism], f"switch-plate-{cfg.trigger}")
    for name in names:
        part = oriented(cfg, name)
        assert checks.overhangs(name, part) == [], name
        assert checks.bed_fit(name, part, cfg.printer.volume) == [], name


@pytest.mark.parametrize("cfg", MECHANISM_CONFIGS, ids=_id)
def test_the_module_sits_in_the_grip_held_by_one_bolt(cfg):
    a = assembly(cfg)
    m = meshes(cfg)
    housing = catalog.MECHANISM_PARTS[cfg.mechanism][0]
    assert intersection_volume(m[housing], m["grip"]) < 1.0
    assert intersection_volume(m[housing], m["receiver"]) < 1.0
    teardown = [b for b in a.bought if b.module == "trigger" and b.teardown]
    assert [(b.label, b.key) for b in teardown] == [("trigger bolt", "m3x12")]
    assert m["trigger bolt"].min_gap(m["nut, trigger bolt"], 1.0) < 0.05


@pytest.mark.parametrize("cfg", MECHANISM_CONFIGS, ids=_id)
def test_the_mounting_bolt_is_reached_from_below(cfg):
    """A hex key goes straight up to its head, past every printed part."""
    key = to_manifold(T.key_way())
    assert checks.overlapping(key, _printed(cfg), "hex key", "trigger bolt") == []


def test_every_mechanism_shares_the_plates_and_switch():
    from boresight_case.export import part_signature

    for trigger in ("mx", "microswitch"):
        seen = set()
        for mechanism in ("bolt", "button"):
            a = assembly(Config(mechanism=mechanism, trigger=trigger))
            plate = a.printed[f"switch-plate-{trigger}"]
            seen.add(
                (
                    part_signature(plate.oriented()),
                    a.bought_by_label()["trigger switch"].key,
                )
            )
        assert len(seen) == 1, seen


# -- the lever ------------------------------------------------------------------------


@pytest.mark.parametrize("cfg", LEVERS, ids=_id)
def test_the_blades_travel_clears_every_printed_part(cfg):
    """From rest to the stop, the blade touches nothing printed: only the
    switch, which its tail presses, and the spring."""
    sweep = to_manifold(T.lever_sweep(cfg.trigger))
    others = {n: mm for n, mm in _printed(cfg).items() if n != "trigger-blade"}
    assert checks.overlapping(sweep, others, "lever travel", "blade") == []


@pytest.mark.parametrize("style", ("minimal", "blaster"))
def test_the_blades_travel_clears_the_covers(style):
    cfg = Config(style=style)
    a = assembly(cfg, True)
    sweep = to_manifold(T.lever_sweep("mx"))
    covers = {
        n: mm
        for n, mm in meshes(cfg, True).items()
        if n in a.printed and a.printed[n].kind != "core"
    }
    assert checks.overlapping(sweep, covers, "lever travel", "blade") == []


@pytest.mark.parametrize("trigger", ("mx", "microswitch"))
def test_the_default_stop_is_past_actuation_and_short_of_end_of_travel(trigger):
    actuate, end = T.switch_limits(trigger)
    stop = T.pad_travel(T.angle_for_travel(L.STOP_TRAVEL[trigger]))
    assert actuate < stop < end


def test_at_rest_the_tail_just_touches_the_switch():
    assert T.pad_travel(0.0) == pytest.approx(0.0)
    assert T.MX_FACE_X - MX_STEM_TOP == pytest.approx(T.CONTACT_X)


@pytest.mark.parametrize("cfg", LEVERS, ids=_id)
def test_the_stop_screw_meets_the_arm_at_the_stop(cfg):
    """Just short of the stop angle the blade's arm clears the screw; just
    past it, the arm runs into it."""
    screw = meshes(cfg)["stop screw"]
    stop = T.angle_for_travel(L.STOP_TRAVEL[cfg.trigger])
    before = to_manifold(T.lever_shape(stop - math.radians(0.5)))
    after = to_manifold(T.lever_shape(stop + math.radians(1.5)))
    assert intersection_volume(before, screw) < 0.05
    assert intersection_volume(after, screw) > 0.3


@pytest.mark.parametrize("cfg", LEVERS, ids=_id)
def test_the_spring_holds_the_blade_against_the_switch(cfg):
    """The return spring bears on the blade's back below the pivot, so it
    turns the tail back off the switch."""
    m = meshes(cfg)
    assert m["return spring"].min_gap(m["trigger-blade"], 0.5) < 0.05
    spring = assembly(cfg).bought_by_label()["return spring"].shape.bounding_box()
    assert spring.center().Z < T.P.Z  # below the pivot


@pytest.mark.parametrize("trigger", ("mx", "microswitch"))
def test_the_pivot_bolt_runs_through_the_blade_into_its_nut(trigger):
    m = meshes(Config(trigger=trigger))
    bolt, nut = m["pivot bolt"], m["nut, pivot bolt"]
    assert intersection_volume(bolt, m["trigger-blade"]) < 0.05
    assert intersection_volume(bolt, m["trigger-housing-bolt"]) < 0.05
    assert bolt.min_gap(nut, 1.0) < 0.05
    lo, hi = bolt.bounding_box()[1], bolt.bounding_box()[4]
    assert -L.TRIGGER_HALF_W < lo and hi < L.TRIGGER_HALF_W


@pytest.mark.parametrize("mechanism", ("bolt", "button"))
def test_the_reach_from_the_grips_back_is_60_to_70_mm(mechanism):
    """At the finger's height, from the grip's back to the face it pulls."""
    z = T.P.Z - L.SPRING_R
    face = T.CONTACT_X + 1.0 if mechanism == "bolt" else B.FRONT_X
    reach = face - L.grip_back_x(z)
    assert 60.0 <= reach <= 70.0, reach


# -- the push button ------------------------------------------------------------------


@pytest.mark.parametrize("cfg", BUTTONS, ids=_id)
def test_the_buttons_travel_clears_every_printed_part(cfg):
    sweep = to_manifold(B.button_sweep(cfg.trigger))
    others = {n: mm for n, mm in _printed(cfg).items() if n != "button-plunger"}
    assert checks.overlapping(sweep, others, "button travel", "button") == []


@pytest.mark.parametrize("cfg", BUTTONS, ids=_id)
def test_the_button_stops_past_actuation_and_short_of_end_of_travel(cfg):
    """Pressed just short of the plate's stop travel the plunger clears the
    stop screw; just past it, its pad runs into the screw's head."""
    screw = meshes(cfg)["stop screw"]
    travel = L.STOP_TRAVEL[cfg.trigger]
    actuate, end = T.switch_limits(cfg.trigger)
    assert actuate < travel < end
    before = to_manifold(B.plunger_shape(travel - 0.05))
    after = to_manifold(B.plunger_shape(travel + 0.3))
    assert intersection_volume(before, screw) < 0.05
    assert intersection_volume(after, screw) > 0.3


@pytest.mark.parametrize("cfg", BUTTONS, ids=_id)
def test_the_button_meets_the_switch_on_its_contact_line(cfg):
    """At rest the plunger's head is on the switch's line, so the button
    moves exactly as far as the switch does."""
    m = meshes(cfg)
    assert m["button-plunger"].min_gap(m["trigger switch"], 1.0) < 0.05


@pytest.mark.parametrize("cfg", BUTTONS, ids=_id)
def test_the_button_returns_on_its_spring(cfg):
    m = meshes(cfg)
    assert m["return spring"].min_gap(m["button-plunger"], 0.5) < 0.05


def test_switch_plates_share_the_seat():
    """Both plates have the same outline where they slide into the
    housing, so either fits every mechanism."""
    from boresight_case.geom import box

    fit = Fit()
    seat = T._plate_outline(fit).bounding_box()
    # In the right-hand groove, where neither plate has anything of its own.
    slab = box(T.PLATE_X[0], T.PLATE_X[1] - 0.05, -20, -T.INNER, -80, 0)
    for plate in (T.mx_plate(fit), T.micro_carrier(fit)):
        bb = (plate & slab).bounding_box()
        assert bb.min.Y == pytest.approx(seat.min.Y)
        assert bb.min.Z == pytest.approx(seat.min.Z)
        assert bb.max.Z == pytest.approx(seat.max.Z)
