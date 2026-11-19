"""The bones: receiver, barrel, grip and rear cap (tasks 3.3, 4.1 to 4.3)."""

import pytest
from conftest import assembly, meshes, oriented

from boresight_case import checks
from boresight_case import layout as L
from boresight_case.config import Config
from boresight_case.interfaces import Fit
from boresight_case.joints import BACKSTRAP_BOLT, GRIP_BOLT, RECEIVER_PORT
from boresight_case.mesh import intersection_volume, to_manifold
from boresight_case.parts.barrel import barrel
from boresight_case.parts.grip import grip
from boresight_case.parts.rear_cap import rear_cap
from boresight_case.parts.receiver import receiver

BONES = ("receiver", "barrel", "grip", "rear-cap")
CFG = Config()


@pytest.mark.parametrize("name", BONES)
def test_a_bone_is_one_solid(name):
    shape = assembly(CFG).printed[name].shape
    assert shape.is_valid and len(shape.solids()) == 1


@pytest.mark.parametrize("name", BONES)
def test_a_bone_fits_the_bed_and_prints_without_support(name):
    part = oriented(CFG, name)
    assert checks.bed_fit(name, part, CFG.printer.volume) == []
    assert checks.overhangs(name, part) == []


@pytest.mark.parametrize(
    "bone", (receiver, barrel, grip, rear_cap), ids=lambda f: f.__name__
)
def test_a_bone_carries_nothing_bought(bone):
    """A bone taken out of a gun has no purchased part attached: every
    nut belongs to its bolt's module."""
    m = bone(Fit())
    assert m.bought == []


def test_every_barrel_is_the_same_part():
    a = assembly(Config(barrels=2))
    first, second = a.printed["barrel"], a.printed["barrel 2"]
    assert first.part == second.part == "barrel"
    assert first.shape.volume == pytest.approx(second.shape.volume)
    dx = second.shape.bounding_box().min.X - first.shape.bounding_box().min.X
    assert dx == pytest.approx(L.BARREL_LEN)


def test_core_modules_assemble_without_interference(core_config):
    a = assembly(core_config)
    m = meshes(core_config)
    problems = checks.interference(m, a.press_fits)
    assert problems == [], "\n".join(p.text() for p in problems)


def test_declared_press_fits_are_slivers(core_config):
    """A declared fit may overlap a little (a nut in its pocket, a plug on
    its pins), never a lot: a gross collision is not hidden by a fit."""
    a = assembly(core_config)
    m = meshes(core_config)
    for pair in a.press_fits:
        p, q = sorted(pair)
        if "plug" in p or "plug" in q:
            continue  # a plug engulfs its pins, or a port, by design
        if p in m and q in m:
            overlap = intersection_volume(m[p], m[q])
            assert overlap < 120, f"{p} / {q} overlap {overlap:.0f} mm^3"


def test_neither_grip_bolt_crosses_the_drawer_bay():
    from boresight_case.joints import BAY_SLIDE

    bay = to_manifold(BAY_SLIDE.pocket())
    for b in (GRIP_BOLT, BACKSTRAP_BOLT):
        assert intersection_volume(to_manifold(b.sweep(0.5)), bay) < 0.01, b.name


def test_the_grip_bolt_crosses_the_tenon_through_its_crush_bar():
    m = meshes(CFG)
    bolt = m["grip bolt"]
    assert intersection_volume(bolt, m["grip"]) < 0.5
    assert intersection_volume(bolt, m["receiver"]) < 0.5
    bar = to_manifold(GRIP_BOLT.crush_tube(-12, 12, (0, 0, 1)))
    assert intersection_volume(bar, m["grip"]) > 0.6 * bar.volume()


def test_the_trigger_housing_mates_its_pocket_with_the_clearance():
    from boresight_case.mesh import min_gap

    for mechanism in ("bolt", "button"):
        cfg = Config(mechanism=mechanism)
        m = meshes(cfg)
        housing = f"trigger-housing-{mechanism}"
        assert intersection_volume(m[housing], m["grip"]) < 0.5
        gap = min_gap(m[housing], m["grip"])
        assert 0.05 < gap < 1.0, (mechanism, gap)


def test_a_remixed_barrel_fits_the_receiver():
    """Any barrel built on the standard tenon seats in the receiver's port:
    here, a plain tube carrying only the tenon."""
    from boresight_case.geom import NEG_X, box

    fit = Fit()
    plain = box(0, 60, -18, 18, -25, 25) - box(-1, 61, -15.5, 15.5, -22.5, 22.5)
    remix = plain + RECEIVER_PORT.tenon(fit, NEG_X)
    assert intersection_volume(to_manifold(remix), meshes(CFG)["receiver"]) < 1.0


@pytest.mark.parametrize("barrels", (0, 1, 2))
def test_the_core_assembles_with_every_barrel_count(barrels):
    cfg = Config(barrels=barrels)
    a = assembly(cfg)
    assert a.part_counts().get("barrel", 0) == barrels
    assert checks.interference(meshes(cfg), a.press_fits) == []
