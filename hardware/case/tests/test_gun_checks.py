"""Steel only, and bolts clear of what works (tasks 5.1 to 5.4)."""

import pytest
from build123d import Location
from conftest import assembly, everything, meshes

from boresight_case import bom, gun_checks
from boresight_case.config import Config, shipped_configurations
from boresight_case.interfaces import ThroughBolt
from boresight_case.joints import barrel_port
from boresight_case.mesh import to_manifold

ALL = shipped_configurations()


@pytest.mark.parametrize("cfg", ALL, ids=lambda c: c.name)
def test_no_bolt_crosses_a_module_a_lead_or_the_view(cfg):
    problems = gun_checks.bolt_clearance(assembly(cfg), everything(cfg))
    assert problems == [], "\n".join(p.text() for p in problems)


@pytest.mark.parametrize("cfg", ALL, ids=lambda c: c.name)
def test_no_metal_within_10_mm_of_the_antenna(cfg):
    problems = gun_checks.antenna(assembly(cfg), meshes(cfg))
    assert problems == [], "\n".join(p.text() for p in problems)


def test_a_bolt_across_the_pi_sled_fails_naming_the_bolt_and_the_sled():
    cfg = Config(board="pi-zero-2w")
    a = assembly(cfg)
    stray = ThroughBolt("stray bolt", (40.0, 0, 15.0))
    a2 = type(a)(
        a.config, a.printed, a.bought, a.press_fits, [stray], a.leads, a.extras
    )
    hits = gun_checks.bolt_clearance(a2, everything(cfg))
    assert ("stray bolt", "sled-pi-zero-2w") in {p.parts for p in hits}


def test_muzzle_bolts_near_the_esp32_antenna_fail_naming_bolt_board_and_zone():
    cfg = Config()
    a = assembly(cfg)
    m = dict(meshes(cfg))
    # Move the muzzle port's lower bolt 20 mm forward, to the antenna.
    bolt = next(b for b in a.bought if b.label == barrel_port(0).bolts[1].name)
    moved = Location((22.0, 0, -4.0)) * bolt.shape
    m[bolt.label] = to_manifold(moved)
    hits = gun_checks.antenna(a, m)
    assert any(p.parts == (bolt.label, "esp32-cam", "antenna zone") for p in hits)


def test_the_pi_antenna_is_10_mm_from_the_nearest_bolts():
    """The open check: the Pi's antenna against the barrel's rear and muzzle
    ports' bolts, for every Pi configuration (by the test above), and here
    with its margin."""
    from boresight_case.keepouts import antenna_solids

    for barrels in (1, 2):
        cfg = Config(board="pi-zero-2w", barrels=barrels)
        dx = (barrels - 1) * 100.0
        antenna = to_manifold(Location((dx, 0, 0)) * antenna_solids()["pi-zero-2w"])
        nearest = min(
            antenna.min_gap(meshes(cfg)[b.name], 30.0) for b in assembly(cfg).bolts
        )
        assert nearest >= 10.0, nearest


@pytest.mark.parametrize(
    "cfg, count",
    [
        (Config(), 9),
        (Config(barrels=2), 11),
        (Config(barrels=0), 7),
        (Config(board="pi-zero-2w", barrels=2, mechanism="button"), 11),
    ],
    ids=lambda x: str(x) if isinstance(x, int) else x.name,
)
def test_a_teardown_undoes_the_bolt_budget_in_two_lengths(cfg, count):
    teardown = bom.teardown_bolts(assembly(cfg, True))
    assert sum(teardown.values()) == count <= 12
    assert set(teardown) == {"m3x50", "m3x12"}
    assert teardown["m3x12"] == 1  # the trigger's


@pytest.mark.parametrize("cfg", ALL, ids=lambda c: c.name)
def test_every_through_bolt_takes_a_lock_nut(cfg):
    a = assembly(cfg)
    labels = {b.label: b.key for b in a.bought}
    for b in a.bolts:
        assert labels[b.name] == "m3x50"
        assert labels[f"nut, {b.name}"] == "m3-nyloc"
