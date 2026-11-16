"""Writing a configuration's outputs: the files a builder prints from, the
STEP files a remixer opens, the skin interface, the bill of materials and
the exploded view.

    <out>/
      parts/<part>.stl, <part>.3mf   each part on the bed, ready to slice
      step/<part>.step               each part where it sits in the gun
      step/assembly.step             the whole gun, purchased parts included
      interface/skin-interface.step  the core's envelope, every keep-out zone
                                     and attachment point, as named solids
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
from boresight_case.geom import cylinder, oriented_box, v
from boresight_case.interfaces import HOOK_LIP, SKIN_CBORE_DEPTH, SKIN_T
from boresight_case.joints import ATTACHMENTS
from boresight_case.keepouts import core_envelope, zones
from boresight_case.mesh import to_manifold, write_3mf
from boresight_case.vendor import M3_CLEAR, M3_HEAD_CBORE


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
    for name, p in a.printed.items():
        write_mesh(p.oriented(), parts / name)
        export_step(_labelled(p.shape, name), str(step / f"{name}.step"))
    children = [_labelled(p.shape, n) for n, p in a.printed.items()]
    children += [_labelled(b.shape, f"{b.label} ({b.key})") for b in a.bought]
    export_step(
        Compound(children=children, label=a.config.name), str(step / "assembly.step")
    )


def interface_data(cfg: Config) -> dict:
    """The skin interface as numbers: what a skin may touch and where it
    must not go."""
    points = []
    for (section, side), a in ATTACHMENTS.items():
        face, n = a.screw_axis()
        points.append(
            {
                "name": a.name,
                "section": section,
                "side": side,
                "screw": {
                    "position": [round(c, 3) for c in face],
                    "axis": [round(c, 4) for c in n],
                    "screw": "M3 x 8 socket head",
                    "clearance_hole": M3_CLEAR,
                    "counterbore": {
                        "diameter": M3_HEAD_CBORE,
                        "depth": SKIN_CBORE_DEPTH,
                    },
                },
                "hook": {
                    "position": [round(c, 3) for c in a.hook],
                    "wall_normal": [round(c, 4) for c in (a.hook_normal or a.normal)],
                    "slide": [round(c, 4) for c in a.slide],
                    "stem": list(a.stem),
                    "wedge": HOOK_LIP,
                },
            }
        )
    zone_list = []
    for name, z in zones().items():
        bb = z.bounding_box()
        zone_list.append(
            {
                "name": name,
                "bounds": [
                    [round(bb.min.X, 2), round(bb.min.Y, 2), round(bb.min.Z, 2)],
                    [round(bb.max.X, 2), round(bb.max.Y, 2), round(bb.max.Z, 2)],
                ],
            }
        )
    return {
        "configuration": cfg.name,
        "units": "mm; x forward along the camera axis, y to the gun's left, z up",
        "skin_flank_thickness": SKIN_T,
        "core_flank": {"body": L.HALF_W, "grip": L.GRIP_WIDTH / 2},
        "print": {
            "orientation": "flank down",
            "max_overhang_degrees_from_vertical": 45,
            "max_bridge_mm": 10,
        },
        "attachment_points": points,
        "keep_out_zones": zone_list,
        "geometry": "skin-interface.step holds the core envelope, every zone "
        "and every attachment point as a named solid",
    }


def write_interface(cfg: Config, out: Path) -> None:
    d = out / "interface"
    d.mkdir(parents=True, exist_ok=True)
    children = [_labelled(core_envelope(), "core envelope")]
    children += [_labelled(z, f"keep-out: {n}") for n, z in zones().items()]
    for a in ATTACHMENTS.values():
        face, n = a.screw_axis()
        children.append(
            _labelled(
                cylinder(face - n * 3.0, n, M3_CLEAR / 2, 6.0),
                f"attachment: {a.name} screw",
            )
        )
        hn = v(a.hook_normal or a.normal)
        s = v(a.slide)
        t = hn.cross(s).normalized()
        children.append(
            _labelled(
                oriented_box(v(a.hook) - hn * 1.0, s, t, (a.stem[0], a.stem[1], 2.0)),
                f"attachment: {a.name} hook",
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
    """What makes two parts the same: their volume and their extent."""
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
        for name, p in a.printed.items():
            sig = part_signature(p.shape)
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
