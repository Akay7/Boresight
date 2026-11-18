"""The build's outputs: meshes, STEP, interface, bill of materials, drawing,
`--all` and the coupon (tasks 10.1 to 10.4)."""

import json
from collections import Counter
from functools import cache
from pathlib import Path

import pytest
from conftest import assembly

from boresight_case import bom, catalog, cli, drawing
from boresight_case.config import Config, shipped_configurations
from boresight_case.coupon import coupon_parts, filament_grams
from boresight_case.export import build_configuration
from boresight_case.joints import through_bolts
from boresight_case.keepouts import metal_zones, zones
from boresight_case.mesh import load_mesh_file

PI = Config(board="pi-zero-2w", power="18650", feedback="lra", buttons=True)
ALL = shipped_configurations()


@cache
def built(tmp_root: str) -> Path:
    return build_configuration(PI, Path(tmp_root) / PI.name)


@pytest.fixture(scope="module")
def out(tmp_path_factory) -> Path:
    return built(str(tmp_path_factory.mktemp("case")))


def test_build_holds_exactly_the_parts_the_configuration_needs(out):
    stems = {p.stem for p in (out / "parts").glob("*.stl")}
    assert stems == set(catalog.part_names(PI))
    assert {p.stem for p in (out / "parts").glob("*.3mf")} == stems
    step_stems = {p.stem for p in (out / "step").glob("*.step")}
    assert step_stems == stems | {"assembly"}
    assert not any("esp32" in s or s.startswith(("drawer-a", "nose")) for s in stems)
    assert {"feedback-lra", "button-panel", "cable-clamp", "pi-retainer"} <= stems


def test_every_mesh_lies_on_the_bed(out):
    for stl in (out / "parts").glob("*.stl"):
        lo = load_mesh_file(stl).bounding_box()[2]
        assert abs(lo) < 0.01, stl.name
    for tmf in list((out / "parts").glob("*.3mf"))[:3]:
        assert load_mesh_file(tmf).volume() > 0


def test_3mf_files_are_valid_for_slicers(out):
    """Read back with lib3mf, the 3MF consortium's own library."""
    import lib3mf

    wrapper = lib3mf.get_wrapper()
    for tmf in (out / "parts").glob("*.3mf"):
        model = wrapper.CreateModel()
        model.QueryReader("3mf").ReadFromFile(str(tmf))
        meshes = model.GetMeshObjects()
        assert meshes.MoveNext(), tmf.name
        assert meshes.GetCurrentMeshObject().IsManifoldAndOriented(), tmf.name


def test_interface_lists_every_bolt_and_zone(out):
    data = json.loads((out / "interface" / "skin-interface.json").read_text())
    assert {b["name"] for b in data["bolts"]} == {
        b.name for b in through_bolts(PI.barrels)
    }
    for b in data["bolts"]:
        assert b["flange"] == 3.0 and b["axis"] == [0.0, -1.0, 0.0]
        assert b["nut_pocket"]["side"] == "right"
    names = {(z["name"], z["applies_to"]) for z in data["keep_out_zones"]}
    assert {n for n, k in names if k == "all"} == set(zones(PI))
    assert {n for n, k in names if k == "metal"} == set(metal_zones(PI))
    assert (out / "interface" / "skin-interface.step").stat().st_size > 10_000


def test_bom_lists_every_part_with_its_count(out):
    a = assembly(PI, True)
    lines = bom.lines(a)
    printed = {ln.name: ln.count for ln in lines if ln.kind == "print"}
    assert printed == dict(catalog.part_counts(PI))
    bought = {ln.name: ln.count for ln in lines if ln.kind == "buy"}
    assert bought == dict(Counter(b.key for b in a.bought))
    text = (out / "bom.md").read_text()
    assert "PETG" in text and "trigger-blade" in text and "M3 x 50" in text
    assert "## Leads" in text
    assert (
        (out / "bom.csv").read_text().startswith("kind,part,file,count,specification")
    )


def test_an_aa_esp32_cam_gun_lists_every_bolt_and_nut_with_none_over():
    a = assembly(Config(power="aa"), True)
    bought = Counter(b.key for b in a.bought)
    assert bought["m3x50"] == bought["m3-washer"] == len(a.bolts) == 8
    assert bought["m3-nyloc"] == 8 + 1  # and the trigger's stop screw
    nuts = [b for b in a.bought if b.key == "m3-nut"]
    screws = [
        b for b in a.bought if b.key in ("m3x12", "m3-thumbscrew", "m3-thumbscrew-16")
    ]
    # Every plain nut has its screw: the trigger's, its pivot's, the
    # thumbscrew's.
    assert len(nuts) == len([s for s in screws if "stop" not in s.label])


def test_the_lra_wiring_names_its_pins():
    rows = [ln for ln in bom.lines(assembly(PI, True)) if ln.name == "feedback lead"]
    assert rows and all(f"pin {n}" in rows[0].spec for n in (1, 3, 5))


@pytest.mark.parametrize("cfg", ALL, ids=lambda c: c.name)
def test_teardown_takes_at_most_twelve_bolts_in_two_lengths(cfg):
    a = assembly(cfg, True)
    teardown = bom.teardown_bolts(a)
    assert sum(teardown.values()) <= 12
    assert set(teardown) == {"m3x50", "m3x12"}
    assert set(bom.bolts(a)) <= {"m3x50", "m3x12"}


def test_a_part_name_always_means_the_same_geometry():
    from boresight_case.export import part_signature

    seen = {}
    for cfg in ALL:
        for p in assembly(cfg, True).printed.values():
            sig = part_signature(p.oriented())
            assert seen.setdefault(p.part, sig) == sig, (p.part, cfg.name)


@pytest.fixture(scope="module")
def library(tmp_path_factory) -> Path:
    from boresight_case.export import build_library

    # One configuration of each mechanism and kit: every kind of part.
    sample = [
        Config(),
        Config(board="pi-zero-2w", power="usb", trigger="microswitch", barrels=2),
        Config(power="18650", mechanism="button", style="blaster", feedback="solenoid"),
    ]
    return build_library(sample, tmp_path_factory.mktemp("library"))


def test_library_holds_each_part_once_and_every_bom_names_only_its_files(library):
    stl = {p.name for p in (library / "parts").glob("*.stl")}
    configs = sorted((library / "configurations").iterdir())
    assert len(configs) == 3
    for d in configs:
        assert {"bom.md", "bom.csv", "exploded.svg"} <= {p.name for p in d.iterdir()}
        rows = (d / "bom.csv").read_text().splitlines()[1:]
        files = [r.split(",")[2] for r in rows if r.startswith("print,")]
        assert files and all(f.startswith("parts/") for f in files)
        assert {f.removeprefix("parts/") for f in files} <= stl, d.name
    assert (library / "interface" / "skin-interface.json").exists()
    assert not list(library.glob("*/step/assembly.step"))


@pytest.mark.parametrize("cfg", ALL[::7], ids=lambda c: c.name)
def test_exploded_view_names_every_part(cfg):
    a = assembly(cfg, True)
    svg = drawing.exploded_svg(a)
    assert svg.startswith("<svg") and "<polyline" in svg
    for name in drawing.drawn(a):
        assert f">{name}</text>" in svg, name


def test_build_all_builds_the_library_of_every_configuration(
    tmp_path, monkeypatch, capsys
):
    import boresight_case.export as export

    built = []

    def fake(configs, out, progress=None):
        built.extend(cfg.name for cfg in configs)
        return out

    monkeypatch.setattr(export, "build_library", fake)
    assert cli.main(["build", "--all", "--out", str(tmp_path)]) == 0
    assert sorted(built) == sorted(c.name for c in ALL)
    assert len(built) == 103


def test_coupon_is_small_and_prints_without_support():
    from boresight_case import checks
    from boresight_case.mesh import to_manifold

    assert filament_grams() < 10.0
    for p in coupon_parts():
        o = to_manifold(p.oriented())
        assert checks.overhangs(p.name, o) == []
        assert checks.bed_fit(p.name, o, (180, 180, 180)) == []


def test_coupon_command_writes_its_parts(tmp_path):
    assert cli.main(["coupon", "--out", str(tmp_path)]) == 0
    names = {p.name for p in (tmp_path / "coupon").iterdir()}
    assert {"coupon-sockets.stl", "coupon-pegs.3mf", "README.md"} <= names
