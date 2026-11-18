"""`check-skin` on covers supplied as files (task 13.3), and the zones it
holds them to (task 13.2)."""

from pathlib import Path

import pytest
from build123d import export_stl
from conftest import assembly

from boresight_case import cli
from boresight_case import layout as L
from boresight_case.config import Config
from boresight_case.geom import box, cylinder
from boresight_case.interfaces import FLANGE
from boresight_case.joints import RECEIVER_PORT
from boresight_case.keepouts import zones
from boresight_case.mesh import to_manifold
from boresight_case.skin_check import check_skin, check_skin_files

CFG = Config(style="minimal")
NAME = "skin-minimal-receiver-right"


def _write(shape, path: Path) -> Path:
    export_stl(shape, str(path), tolerance=0.02)
    return path


@pytest.fixture(scope="module")
def skin():
    return assembly(CFG, True).printed[NAME].shape


def test_an_exported_cover_conforms(skin, tmp_path):
    report = check_skin_files(CFG, [_write(skin, tmp_path / "mine.stl")])
    assert report.ok, report.text()
    assert "ok   mine.stl: conforms" in report.text()


def test_a_cover_over_the_switch_fails_naming_the_part_and_zone(tmp_path):
    left = assembly(CFG, True).printed["skin-minimal-receiver-left"].shape
    x, z = L.SWITCH_AT
    plate = box(x - 6, x + 6, L.HALF_W + 0.2, L.HALF_W + FLANGE, z - 6, z + 6)
    report = check_skin_files(CFG, [_write(left + plate, tmp_path / "blocked.stl")])
    hits = [p for p in report.problems if p.check == "keep-out"]
    assert hits and hits[0].parts == ("blocked.stl", "switch, LEDs and buttons")
    assert "blocked.stl" in report.text()


def test_a_filled_bolt_hole_fails_naming_the_bolt(skin, tmp_path):
    b = RECEIVER_PORT.bolts[0]
    x, _, z = b.centre
    plug = cylinder((x, -L.HALF_W, z), (0, -1, 0), 1.9, FLANGE)
    report = check_skin_files(CFG, [_write(skin + plug, tmp_path / "plugged.stl")])
    hits = [
        p for p in report.problems if p.check == "bolt" and "clear hole" in p.detail
    ]
    assert (("plugged.stl", b.name)) in [p.parts for p in hits]


def test_a_flange_of_the_wrong_thickness_fails(skin, tmp_path):
    b = RECEIVER_PORT.bolts[0]
    x, _, z = b.centre
    thin = skin - box(
        x - 5, x + 5, -L.HALF_W - FLANGE - 1, -L.HALF_W - 0.5, z - 5, z + 5
    )
    report = check_skin_files(CFG, [_write(thin, tmp_path / "thin.stl")])
    assert any("thinner" in p.detail for p in report.problems)
    thick = skin + (
        cylinder((x, -L.HALF_W - FLANGE, z), (0, -1, 0), 3.4, 2.0)
        - cylinder((x, -L.HALF_W - FLANGE + 1, z), (0, -1, 0), 2.0, 4.0)
    )
    report = check_skin_files(CFG, [_write(thick, tmp_path / "thick.stl")])
    assert any("thicker" in p.detail for p in report.problems)


def test_a_cover_with_a_hook_fails(skin, tmp_path):
    """A hook reaching through a bone's wall enters the core."""
    hook = box(-60, -56, -L.HALF_W - 0.5, -L.HALF_W + 3.0, 0, 4)
    report = check_skin_files(CFG, [_write(skin + hook, tmp_path / "hooked.stl")])
    assert any(
        p.check == "core envelope" and "hook" in p.detail for p in report.problems
    )


def test_an_oversized_cover_fails_the_bed(tmp_path):
    huge = box(-300, -100, 30, 40, 40, 50)
    report = check_skin_files(CFG, [_write(huge, tmp_path / "huge.stl")])
    assert any(p.check == "bed" for p in report.problems)


@pytest.mark.parametrize("zone", sorted(zones(Config())))
def test_a_part_entering_each_zone_fails_naming_it(zone):
    """A lump of a cover just inside each zone, outside the core."""
    z = to_manifold(zones(CFG)[zone])
    from boresight_case.keepouts import core_envelope

    probe = (z - to_manifold(core_envelope(CFG))).bounding_box()
    lo = probe[:3]
    lump = to_manifold(box(lo[0], lo[0] + 3, lo[1], lo[1] + 3, lo[2], lo[2] + 3)) ^ (
        z - to_manifold(core_envelope(CFG))
    )
    hits = [p for p in check_skin("lump", lump, CFG) if p.check == "keep-out"]
    if lump.volume() > 1.5:
        assert ("lump", zone) in [p.parts for p in hits]


def test_a_metal_part_in_the_antenna_zone_fails_only_as_metal(tmp_path):
    from boresight_case.keepouts import metal_zones

    bb = metal_zones(CFG)["antenna esp32-cam"].bounding_box()
    lump = box(
        bb.min.X + 1,
        bb.min.X + 4,
        -L.HALF_W - 3,
        -L.HALF_W - 0.5,
        bb.min.Z + 1,
        bb.min.Z + 4,
    )
    path = _write(lump, tmp_path / "lump.stl")
    plastic = check_skin_files(CFG, [path])
    metal = check_skin_files(CFG, [path], metal=True)
    assert not any("antenna" in p.parts[-1] for p in plastic.problems)
    assert any(p.parts == ("lump.stl", "antenna esp32-cam") for p in metal.problems)


def test_the_command_exits_by_the_result(skin, tmp_path, capsys):
    cfg_file = tmp_path / "gun.toml"
    cfg_file.write_text('[build]\nstyle = "minimal"\n')
    good = _write(skin, tmp_path / "good.stl")
    assert cli.main(["check-skin", str(cfg_file), str(good)]) == 0
    bad = tmp_path / "bad.stl"
    bad.write_text("not a mesh")
    assert cli.main(["check-skin", str(cfg_file), str(bad)]) == 1
    assert "FAIL bad.stl" in capsys.readouterr().out
