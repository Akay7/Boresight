"""The checks that look at a whole gun: its bolts against what works, and
every metal part against the board's antenna.

Each takes an assembly and its parts as meshes (by printed name, purchased
label and lead name) and returns a list of Problems, empty when it passes.
"""

from __future__ import annotations

from collections.abc import Mapping

import manifold3d as m3

from boresight_case.assembly import Assembly
from boresight_case.checks import Problem, overlapping, too_close
from boresight_case.mesh import to_manifold

# The bolt crosses these by design: the bones, the parts that fill a port
# (their crush tubes take its clamp), the covers and the collars.
PORT_PARTS = ("receiver", "barrel", "grip", "rear-cap", "camera-pi", "nose-")
ANTENNA_CLEARANCE = 10.0


def _crossed(name: str, a: Assembly) -> bool:
    p = a.printed.get(name)
    if p is None:
        return False
    return p.kind != "core" or name.startswith(PORT_PARTS) or p.part == "spacer-collar"


def bolt_clearance(
    a: Assembly, meshes: Mapping[str, m3.Manifold], extra: float = 0.5
) -> list[Problem]:
    """Each through-bolt's whole length, grown by `extra`, against every
    module, every purchased part that works, every lead and the camera's
    view."""
    from boresight_case.keepouts import zones

    fasteners = {b.label for b in a.bought if not b.vendor.functional}
    targets = {
        n: mm for n, mm in meshes.items() if n not in fasteners and not _crossed(n, a)
    }
    camera = a.config.camera
    view = zones(a.config).get(f"view {camera}")
    if view is not None:
        targets[f"view {camera}"] = to_manifold(view)
    problems = []
    for b in a.bolts:
        sweep = to_manifold(b.sweep(extra))
        for p in overlapping(sweep, targets, "bolt", b.name, tolerance=0.05):
            problems.append(Problem("bolt", (b.name, p.parts[0]), p.detail))
    return problems


def antenna(a: Assembly, meshes: Mapping[str, m3.Manifold]) -> list[Problem]:
    """No metal part within 10 mm of the board's PCB antenna."""
    from boresight_case import layout as L
    from boresight_case.keepouts import antenna_solids
    from boresight_case.parts import kits

    board = a.config.board
    dx = L.muzzle_x(a.config.barrels) - kits.MUZZLE
    from build123d import Location

    zone = to_manifold(Location((dx, 0, 0)) * antenna_solids()[board])
    own = "ESP32-CAM" if board == "esp32-cam" else "Pi Zero 2 W"
    metal = {
        b.label: meshes[b.label] for b in a.bought if b.vendor.metal and b.label != own
    }
    problems = too_close(f"{board} antenna", zone, metal, ANTENNA_CLEARANCE, "antenna")
    return [
        Problem("antenna", (p.parts[0], board, "antenna zone"), p.detail)
        for p in problems
    ]
