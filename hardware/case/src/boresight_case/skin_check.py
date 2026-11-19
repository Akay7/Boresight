"""Checking cover parts made elsewhere against the skin interface.

Parts come as STL or 3MF in the gun's coordinates, the frame of
`skin-interface.step` (x forward along the camera axis, y left, z up, mm).
Each part is checked: it stays out of the core's envelope (no hook, tab or
peg may reach into the core: a cover is held only by the through-bolts) and
out of every keep-out zone; on each bolt position it covers it has a clear
hole through a flange of the interface's thickness; and it fits the print
bed in some orientation. With `metal`, the antenna zones apply too.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import manifold3d as m3

from boresight_case.checks import INTERFERENCE_TOLERANCE, Problem
from boresight_case.config import Config
from boresight_case.geom import cylinder
from boresight_case.interfaces import FLANGE
from boresight_case.joints import through_bolts
from boresight_case.keepouts import core_envelope, metal_zones, zones
from boresight_case.mesh import (
    MeshError,
    intersection_volume,
    load_mesh_file,
    to_manifold,
)
from boresight_case.skins.base import POCKET

# A flange's annulus round a bolt: inside the washer's and the nut's reach.
RING = (2.4, 3.4)
FILLED = 0.85  # a flange must fill this much of its annulus


@dataclass
class Report:
    parts: list[str] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def text(self) -> str:
        out = []
        for name in self.parts:
            mine = [p for p in self.problems if p.parts[0] == name]
            if mine:
                out += [f"FAIL {name}"] + [f"  {p.check}: {p.detail}" for p in mine]
            else:
                out.append(f"ok   {name}: conforms to the skin interface")
        return "\n".join(out)


def _ring(x: float, z: float, y0: float, y1: float):
    lo, hi = sorted((y0, y1))
    outer = cylinder((x, lo, z), (0, 1, 0), RING[1], hi - lo)
    inner = cylinder((x, lo - 1, z), (0, 1, 0), RING[0], hi - lo + 2)
    return outer - inner


class _Interface:
    def __init__(self, cfg: Config) -> None:
        self.core = to_manifold(core_envelope(cfg))
        self.zones = {n: to_manifold(z) for n, z in zones(cfg).items()}
        self.metal = {n: to_manifold(z) for n, z in metal_zones(cfg).items()}
        self.bolts = []
        for b in through_bolts(cfg.barrels):
            x, _, z = b.centre
            sides = []
            for sign in (1, -1):
                face = sign * b.half
                flank = sign * (b.half + FLANGE)
                bore = to_manifold(
                    cylinder((x, face, z), (0, sign, 0), 1.6, FLANGE + 1.0)
                )
                # On the right, the nut's pocket takes the flange's outer part.
                depth = FLANGE if sign > 0 else FLANGE - POCKET
                flange = to_manifold(_ring(x, z, face, face + sign * depth))
                # Its footprint: a part at a seam covers only part of the ring.
                foot = to_manifold(_ring(x, z, face, face + sign * 0.5))
                beyond = to_manifold(
                    _ring(x, z, flank + sign * 0.3, flank + sign * 3.0)
                )
                sides.append((bore, flange, foot, depth, beyond))
            self.bolts.append((b.name, sides))


_INTERFACES: dict[int, _Interface] = {}


def _interface(cfg: Config) -> _Interface:
    if cfg.barrels not in _INTERFACES:
        _INTERFACES[cfg.barrels] = _Interface(cfg)
    return _INTERFACES[cfg.barrels]


def check_skin(
    name: str, part: m3.Manifold, cfg: Config, metal: bool = False
) -> list[Problem]:
    i = _interface(cfg)
    problems = []
    overlap = intersection_volume(part, i.core)
    if overlap > INTERFERENCE_TOLERANCE:
        problems.append(
            Problem(
                "core envelope",
                (name,),
                f"enters the core by {overlap:.1f} mm^3: a cover may not reach "
                "into it (no hook, tab or peg holds a cover; only the bolts)",
            )
        )
    for zone, zm in list(i.zones.items()) + (list(i.metal.items()) if metal else []):
        overlap = intersection_volume(part, zm)
        if overlap > INTERFERENCE_TOLERANCE:
            problems.append(
                Problem(
                    "keep-out",
                    (name, zone),
                    f"enters the zone '{zone}' by {overlap:.1f} mm^3",
                )
            )
    for bolt, sides in i.bolts:
        for bore, flange, foot, depth, beyond in sides:
            covered = intersection_volume(part, flange)
            if covered < 1.0:
                continue  # the part does not cover this bolt on this side
            area = intersection_volume(part, foot) / 0.5
            if intersection_volume(part, bore) > 0.05:
                problems.append(
                    Problem(
                        "bolt", (name, bolt), f"no clear hole for the bolt '{bolt}'"
                    )
                )
            if covered < FILLED * area * depth:
                problems.append(
                    Problem(
                        "bolt",
                        (name, bolt),
                        f"the flange at '{bolt}' is thinner than {FLANGE:g} mm",
                    )
                )
            if intersection_volume(part, beyond) > 1.0:
                problems.append(
                    Problem(
                        "bolt",
                        (name, bolt),
                        f"the flange at '{bolt}' is thicker than {FLANGE:g} mm",
                    )
                )
    problems += _bed(name, part, cfg.printer.volume)
    return problems


def _bed(name: str, part: m3.Manifold, volume: Sequence[float]) -> list[Problem]:
    bb = part.bounding_box()
    size = sorted(bb[3 + k] - bb[k] for k in range(3))
    if all(s <= v for s, v in zip(size, sorted(volume), strict=True)):
        return []
    return [
        Problem(
            "bed",
            (name,),
            f"{' x '.join(f'{s:.1f}' for s in size)} mm does not fit the "
            f"{' x '.join(f'{v:g}' for v in volume)} mm print volume "
            "in any orientation",
        )
    ]


def check_skin_files(cfg: Config, paths: Sequence[Path], metal: bool = False) -> Report:
    report = Report()
    for path in paths:
        name = path.name
        report.parts.append(name)
        try:
            part = load_mesh_file(path)
        except (OSError, MeshError) as e:
            report.problems.append(Problem("file", (name,), str(e)))
            continue
        report.problems += check_skin(name, part, cfg, metal)
    return report
