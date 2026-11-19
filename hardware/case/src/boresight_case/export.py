"""Writing a configuration's outputs: the files a builder prints from, the
STEP files a remixer opens, the skin interface, the bill of materials and
the exploded view.

    <out>/
      parts/<part>.stl, <part>.3mf   each part on the bed, ready to slice
      step/<part>.step               each part where it sits in the gun
      step/assembly.step             the whole gun, purchased parts included
      interface/skin-interface.step  the core's envelope, every keep-out zone
                                     and through-bolt, as named solids
      interface/skin-interface.json  the same, as numbers
      bom.md, bom.csv                what to print and what to buy
      exploded.svg                   the gun pulled apart, every part named
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from build123d import Compound, Part, export_step, export_stl

from boresight_case import bom, drawing
from boresight_case import layout as L
from boresight_case.assembly import Assembly, build
from boresight_case.config import Config
from boresight_case.geom import cylinder
from boresight_case.interfaces import FLANGE
from boresight_case.joints import through_bolts
from boresight_case.keepouts import core_envelope, metal_zones, zones
from boresight_case.mesh import to_manifold, write_3mf
from boresight_case.skins.base import POCKET
from boresight_case.vendor import M3_CLEAR, M3_NUT_AF, M3_WASHER


def _labelled(shape: Part, label: str) -> Part:
    out = Part(shape.wrapped)
    out.label = label
    return out


def write_mesh(shape: Part, stem: Path) -> None:
    """The part as STL and as 3MF, both from the same closed mesh."""
    export_stl(
        shape, str(stem.with_suffix(".stl")), tolerance=0.02, angular_tolerance=0.15
    )
    write_3mf(to_manifold(shape, 0.02), stem.with_suffix(".3mf"), stem.name)


def write_parts(a: Assembly, out: Path) -> None:
    parts, step = out / "parts", out / "step"
    parts.mkdir(parents=True, exist_ok=True)
    step.mkdir(parents=True, exist_ok=True)
    done = set()
    for p in a.printed.values():
        if p.part in done:
            continue
        done.add(p.part)
        write_mesh(p.oriented(), parts / p.part)
        export_step(_labelled(p.shape, p.part), str(step / f"{p.part}.step"))
    children = [_labelled(p.shape, n) for n, p in a.printed.items()]
    children += [_labelled(b.shape, f"{b.label} ({b.key})") for b in a.bought]
    export_step(
        Compound(children=children, label=a.config.name), str(step / "assembly.step")
    )


def interface_data(cfg: Config) -> dict:
    """The skin interface as numbers: where covers are bolted, and where
    they must not go."""
    bolts = []
    for b in through_bolts(cfg.barrels):
        x, _, z = b.centre
        bolts.append(
            {
                "name": b.name,
                "position": [round(x, 3), 0.0, round(z, 3)],
                "axis": [0.0, -1.0, 0.0],
                "bolt": "M3 x 50 socket head, its head and a washer on the left",
                "core_flank": round(b.half, 3),
                "flange": FLANGE,
                "clear_hole": M3_CLEAR,
                "washer": M3_WASHER[0],
                "nut_pocket": {
                    "side": "right",
                    "across_flats": M3_NUT_AF,
                    "depth": POCKET,
                    "nut": "M3 nylon-insert lock nut",
                },
            }
        )
    zone_list = []
    for kind, zs in (("all", zones(cfg)), ("metal", metal_zones(cfg))):
        for name, z in zs.items():
            bb = z.bounding_box()
            zone_list.append(
                {
                    "name": name,
                    "applies_to": kind,
                    "bounds": [
                        [round(bb.min.X, 2), round(bb.min.Y, 2), round(bb.min.Z, 2)],
                        [round(bb.max.X, 2), round(bb.max.Y, 2), round(bb.max.Z, 2)],
                    ],
                }
            )
    return {
        "configuration": cfg.name,
        "units": "mm; x forward along the camera axis, y to the gun's left, z up",
        "flange_thickness": FLANGE,
        "core_flank": {"body": L.HALF_W, "grip": L.GRIP_WIDTH / 2},
        "print": {
            "orientation": "flank down",
            "max_overhang_degrees_from_vertical": 45,
            "max_bridge_mm": 10,
        },
        "bolts": bolts,
        "keep_out_zones": zone_list,
        "geometry": "skin-interface.step holds the core envelope, every zone "
        "and every through-bolt as a named solid",
    }


def write_interface(cfg: Config, out: Path) -> None:
    d = out / "interface"
    d.mkdir(parents=True, exist_ok=True)
    children = [_labelled(core_envelope(cfg), "core envelope")]
    children += [_labelled(z, f"keep-out: {n}") for n, z in zones(cfg).items()]
    children += [
        _labelled(z, f"keep-out (metal): {n}") for n, z in metal_zones(cfg).items()
    ]
    for b in through_bolts(cfg.barrels):
        x, _, z = b.centre
        children.append(
            _labelled(
                cylinder(
                    (x, b.half + FLANGE, z),
                    (0, -1, 0),
                    M3_CLEAR / 2,
                    2 * (b.half + FLANGE),
                ),
                f"bolt: {b.name} (flange {FLANGE:g} mm each side)",
            )
        )
    export_step(
        Compound(children=children, label="skin interface"),
        str(d / "skin-interface.step"),
    )
    (d / "skin-interface.json").write_text(
        json.dumps(interface_data(cfg), indent=2) + "\n"
    )


def part_signature(shape: Part) -> tuple:
    """What makes two parts the same: their volume and their extent, as
    printed (wherever the gun puts them)."""
    bb = shape.bounding_box()
    return (
        round(shape.volume, 2),
        tuple(
            round(c, 2)
            for c in (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z)
        ),
    )


def build_library(configs: Sequence[Config], out: Path, progress=None) -> Path:
    """Every configuration at once, as a parts library: each distinct part
    once in `parts/` and `step/`, the skin interface once, and for each
    configuration its bill of materials and drawing in
    `configurations/<name>/`. A part's name must always mean the same
    geometry; a clash stops the build."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "parts").mkdir(exist_ok=True)
    (out / "step").mkdir(exist_ok=True)
    seen: dict[str, tuple] = {}
    for cfg in configs:
        a = build(cfg, with_skins=True)
        for p in a.printed.values():
            name = p.part
            sig = part_signature(p.oriented())
            if name in seen:
                if seen[name] != sig:
                    raise AssertionError(
                        f"part {name!r} differs between configurations"
                    )
                continue
            seen[name] = sig
            write_mesh(p.oriented(), out / "parts" / name)
            export_step(_labelled(p.shape, name), str(out / "step" / f"{name}.step"))
        d = out / "configurations" / cfg.name
        d.mkdir(parents=True, exist_ok=True)
        (d / "bom.md").write_text(bom.markdown(a))
        (d / "bom.csv").write_text(bom.csv_text(a))
        (d / "exploded.svg").write_text(drawing.exploded_svg(a))
        if progress:
            progress(cfg)
    write_interface(configs[0], out)
    return out


def build_configuration(cfg: Config, out: Path) -> Path:
    a = build(cfg, with_skins=True)
    out.mkdir(parents=True, exist_ok=True)
    write_parts(a, out)
    write_interface(cfg, out)
    (out / "bom.md").write_text(bom.markdown(a))
    (out / "bom.csv").write_text(bom.csv_text(a))
    (out / "exploded.svg").write_text(drawing.exploded_svg(a))
    return out
