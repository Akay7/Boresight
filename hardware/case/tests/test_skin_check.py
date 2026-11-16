"""`check-skin` on skins supplied as files (task 11.1)."""

from pathlib import Path

import pytest
from build123d import export_stl
from conftest import assembly

from boresight_case import cli
from boresight_case import layout as L
from boresight_case.config import Config
from boresight_case.geom import box, cylinder
from boresight_case.interfaces import SKIN_T
from boresight_case.joints import ATTACHMENTS
from boresight_case.skin_check import check_skin_files

CFG = Config(style="minimal")
NAME = "skin-minimal-receiver-right"


def _write(shape, path: Path) -> Path:
    export_stl(shape, str(path), tolerance=0.02)
    return path


@pytest.fixture(scope="module")
def skin():
    return assembly(CFG, True).printed[NAME].shape


def test_an_exported_skin_conforms(skin, tmp_path):
    report = check_skin_files(CFG, [_write(skin, tmp_path / "mine.stl")])
    assert report.ok, report.text()
    assert "ok   mine.stl: conforms" in report.text()


def test_a_skin_over_the_vents_fails_naming_the_part_and_zone(skin, tmp_path):
    x0, x1 = L.SOC_VENT_X
    plate = box(x0, x1, -L.HALF_W - SKIN_T, -L.HALF_W - 0.2, -4.0, 14.0)
    report = check_skin_files(CFG, [_write(skin + plate, tmp_path / "blocked.stl")])
    assert not report.ok
    hits = [p for p in report.problems if p.check == "keep-out"]
    assert hits and hits[0].parts == ("blocked.stl", "vents")
    assert "blocked.stl" in report.text() and "vents" in report.text()


def test_a_filled_screw_hole_fails_naming_the_attachment_point(skin, tmp_path):
    a = ATTACHMENTS[("receiver", "right")]
    face, n = a.screw_axis()
    plug = cylinder(face, n, 3.0, SKIN_T)
    report = check_skin_files(CFG, [_write(skin + plug, tmp_path / "plugged.stl")])
    hits = [p for p in report.problems if p.check == "attachment"]
    assert [p.parts for p in hits] == [("plugged.stl", "receiver-right")]


def test_a_skin_inside_the_core_fails(tmp_path):
    inside = box(-60, -40, -10, 10, -10, 10)
    report = check_skin_files(CFG, [_write(inside, tmp_path / "inside.stl")])
    assert any(p.check == "core envelope" for p in report.problems)


def test_an_oversized_skin_fails_the_bed(tmp_path):
    huge = box(-300, -100, 30, 40, 40, 50)
    report = check_skin_files(CFG, [_write(huge, tmp_path / "huge.stl")])
    assert any(p.check == "bed" for p in report.problems)


def test_the_command_exits_by_the_result(skin, tmp_path, capsys):
    cfg_file = tmp_path / "gun.toml"
    cfg_file.write_text('[build]\nstyle = "minimal"\n')
    good = _write(skin, tmp_path / "good.stl")
    assert cli.main(["check-skin", str(cfg_file), str(good)]) == 0
    bad = tmp_path / "bad.stl"
    bad.write_text("not a mesh")
    assert cli.main(["check-skin", str(cfg_file), str(bad)]) == 1
    assert "FAIL bad.stl" in capsys.readouterr().out
