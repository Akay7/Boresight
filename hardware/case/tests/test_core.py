"""The core modules: receiver, barrel, grip and rear cap (tasks 5.1, 5.2)."""

import pytest
from conftest import assembly, meshes, oriented

from boresight_case import checks
from boresight_case.config import Config
from boresight_case.interfaces import Fit
from boresight_case.joints import MODULE_JOINTS
from boresight_case.mesh import intersection_volume, to_manifold

CORE = ("receiver", "barrel", "grip", "rear-cap")
CFG = Config()


@pytest.mark.parametrize("name", CORE)
def test_core_part_is_one_solid(name):
    shape = assembly(CFG).printed[name].shape
    assert shape.is_valid and len(shape.solids()) == 1


@pytest.mark.parametrize("name", CORE)
def test_core_part_fits_the_bed(name):
    assert checks.bed_fit(name, oriented(CFG, name), CFG.printer.volume) == []


@pytest.mark.parametrize("name", CORE)
def test_core_part_prints_without_support(name):
    assert checks.overhangs(name, oriented(CFG, name)) == []


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
        if p in m and q in m:
            overlap = intersection_volume(m[p], m[q])
            assert overlap < 120, f"{p} / {q} overlap {overlap:.0f} mm^3"


@pytest.mark.parametrize("joint", MODULE_JOINTS, ids=lambda j: j.name)
def test_each_module_joint_takes_exactly_one_screw(joint):
    screws = [b for b in assembly(CFG).bought if b.label == f"{joint.name} screw"]
    assert len(screws) == 1
    assert screws[0].key == "m3x12" and screws[0].teardown


def test_joint_screw_passes_through_host_and_tenon():
    m = meshes(CFG)
    for joint, tenon in zip(MODULE_JOINTS, ("barrel", "rear-cap", "grip"), strict=True):
        screw = m[f"{joint.name} screw"]
        assert intersection_volume(screw, m["receiver"]) < 1.0
        assert intersection_volume(screw, m[tenon]) < 1.0
        # And it runs through the tenon's nut, in its hole.
        nut = next(n for n in m if n.startswith("nut, ") and joint.name.split()[0] in n)
        assert screw.min_gap(m[nut], 1.0) < 0.1


def test_a_remixed_barrel_fits_the_receiver():
    """Any barrel built on the standard joint seats in the receiver: here,
    a plain tube carrying only the joint's tenon."""
    from boresight_case.geom import NEG_X, box

    fit = Fit()
    joint = MODULE_JOINTS[0]
    plain = box(0, 60, -18, 18, -25, 25) - box(-1, 61, -15.5, 15.5, -22.5, 22.5)
    remix = plain + joint.tenon(fit, NEG_X) - joint.tenon_cuts(fit, NEG_X)
    receiver = meshes(CFG)["receiver"]
    assert intersection_volume(to_manifold(remix), receiver) < 1.0
