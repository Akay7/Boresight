"""Checking skin parts made elsewhere against the skin interface.

Parts come as STL or 3MF in the gun's coordinates, the frame of
`skin-interface.step` (x forward along the camera axis, y left, z up, mm).
Each part is checked: it stays out of the core's envelope and out of every
keep-out zone, it has a clear screw hole on each attachment point it
covers, and it fits the print bed in some orientation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import manifold3d as m3

from boresight_case.checks import INTERFERENCE_TOLERANCE, Problem
from boresight_case.config import Config
from boresight_case.geom import cylinder
from boresight_case.interfaces import SKIN_T
from boresight_case.joints import ATTACHMENTS
from boresight_case.keepouts import core_envelope, zones
from boresight_case.mesh import (
    MeshError,
    intersection_volume,
    load_mesh_file,
    to_manifold,
)


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


class _Interface:
    def __init__(self) -> None:
        self.core = to_manifold(core_envelope())
        self.zones = {n: to_manifold(z) for n, z in zones().items()}
        self.points = []
        for a in ATTACHMENTS.values():
            face, n = a.screw_axis()
            bore = to_manifold(cylinder(face - n * 0.5, n, 1.6, SKIN_T + 1.0))
            area = to_manifold(cylinder(face, n, 6.0, SKIN_T))
            self.points.append((a.name, bore, area))


_INTERFACE: _Interface | None = None


def _interface() -> _Interface:
    global _INTERFACE
    if _INTERFACE is None:
        _INTERFACE = _Interface()
    return _INTERFACE


def check_skin(name: str, part: m3.Manifold, cfg: Config) -> list[Problem]:
    i = _interface()
    problems = []
    overlap = intersection_volume(part, i.core)
    if overlap > INTERFERENCE_TOLERANCE:
        problems.append(
            Problem("core envelope", (name,), f"enters the core by {overlap:.1f} mm^3")
        )
    for zone, zm in i.zones.items():
        overlap = intersection_volume(part, zm)
        if overlap > INTERFERENCE_TOLERANCE:
            problems.append(
                Problem(
                    "keep-out",
                    (name, zone),
                    f"enters the zone '{zone}' by {overlap:.1f} mm^3",
                )
            )
    for point, bore, area in i.points:
        if intersection_volume(part, area) < 20.0:
            continue  # the part does not cover this attachment point
        if intersection_volume(part, bore) > 0.05:
            problems.append(
                Problem(
                    "attachment",
                    (name, point),
                    f"no clear screw hole on attachment point '{point}'",
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


def check_skin_files(cfg: Config, paths: Sequence[Path]) -> Report:
    report = Report()
    for path in paths:
        name = path.name
        report.parts.append(name)
        try:
            part = load_mesh_file(path)
        except (OSError, MeshError) as e:
            report.problems.append(Problem("file", (name,), str(e)))
            continue
        report.problems += check_skin(name, part, cfg)
    return report
