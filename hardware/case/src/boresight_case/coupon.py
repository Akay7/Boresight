"""The fit coupon: a quick print to tune the clearance before the gun.

Two small plates, printed flat:

- `coupon-sockets`: five square sockets, the module joint's fit at
  clearances 0.15, 0.20, 0.25, 0.30 and 0.35 mm, marked by 1 to 5 dots; three
  M3 nut pockets at press fits 0.00, 0.05 and 0.10 mm (1 to 3 dots); the MX
  cut-out in its 1.5 mm web; and a latch notch.
- `coupon-pegs`: a square tenon to try in each socket, pegs for a board's
  2.75 mm hole at the same five clearances (1 to 5 dots), and a latch tongue
  to snap into the notch.

Push the tenon into each socket: the clearance of the one it slides into
without play is the printer's. Set `clearance` in `[printer]` to it. The
nut pocket that holds a nut without forcing gives `interference`.
"""

from __future__ import annotations

from pathlib import Path

from build123d import Part

from boresight_case.config import Printer
from boresight_case.geom import Z, box, cylinder, hexagon_prism, union
from boresight_case.model import PLA_OR_PETG, Printed
from boresight_case.vendor import M3_NUT_AF, MX_CUTOUT, PI_HOLE_D

CLEARANCES = (0.15, 0.20, 0.25, 0.30, 0.35)
INTERFERENCES = (0.0, 0.05, 0.10)
TENON = 6.0
PITCH = 11.0
# PLA's density, for the filament estimate.
PLA_G_PER_MM3 = 1.24e-3


def _dots(x: float, y: float, n: int, z: float) -> Part:
    return union(
        cylinder((x + k * 1.6 - (n - 1) * 0.8, y, z), Z, 0.5, 0.6) for k in range(n)
    )


def sockets() -> Part:
    t = 2.4
    width = PITCH * len(CLEARANCES) + 32
    plate = box(0, width, 0, 26, 0, t)
    cuts, dots = [], []
    for i, c in enumerate(CLEARANCES):
        x = 6 + i * PITCH + TENON / 2
        s = TENON / 2 + c
        cuts.append(box(x - s, x + s, 4 - 0.01, 4 + TENON + 2 * c, -1, t + 1))
        dots.append(_dots(x, 1.6, i + 1, t))
    for i, k in enumerate(INTERFERENCES):
        x = 6 + i * PITCH + TENON / 2
        cuts.append(hexagon_prism((x, 18.0, t / 2 + 0.6), Z, M3_NUT_AF - 2 * k, t))
        cuts.append(cylinder((x, 18.0, -1), Z, 1.7, t + 2))
        dots.append(_dots(x, 24.0, i + 1, t))
    # The MX cut-out: 14 mm through a 1.5 mm web.
    mx_x = 6 + 3 * PITCH + 10
    cuts.append(
        box(mx_x - MX_CUTOUT / 2, mx_x + MX_CUTOUT / 2, 4, 4 + MX_CUTOUT, -1, t + 1)
    )
    cuts.append(box(mx_x - 8, mx_x + 8, 3, 5 + MX_CUTOUT, 1.5, t + 1))
    # The latch notch: the drawer's hook catches its edge.
    notch_x = width - 6
    cuts.append(box(notch_x - 3, notch_x + 3, 19, 26.01, -1, t + 1))
    return plate - union(cuts) + union(dots)


def pegs() -> Part:
    t = 1.6
    width = PITCH * len(CLEARANCES) + 20
    plate = box(0, width, 0, 16, 0, t)
    tenon = box(4, 4 + TENON, 4, 4 + TENON, t - 0.01, t + 5.0)
    holes = []
    dots = []
    for i, c in enumerate(CLEARANCES):
        x = 16 + i * PITCH
        holes.append(cylinder((x, 10, t - 0.01), Z, PI_HOLE_D / 2 - c, 4.0))
        dots.append(_dots(x, 3.0, i + 1, t))
    # The latch tongue and its hook, as on the drawer's base.
    tongue = box(width - 9, width - 3, 2, 14, t - 0.01, t + 1.2) + box(
        width - 9, width - 3, 14, 15, t - 0.01, t + 2.1
    )
    return plate + tenon + union(holes) + union(dots) + tongue


def coupon_parts() -> list[Printed]:
    return [
        Printed(
            "coupon-sockets",
            sockets(),
            Z,
            "coupon",
            kind="coupon",
            material=PLA_OR_PETG,
            perimeters=3,
            infill=20,
        ),
        Printed(
            "coupon-pegs",
            pegs(),
            Z,
            "coupon",
            kind="coupon",
            material=PLA_OR_PETG,
            perimeters=3,
            infill=20,
        ),
    ]


def filament_grams() -> float:
    """An upper bound: the parts' solid volume, as if printed 100% full."""
    return sum(p.shape.volume for p in coupon_parts()) * PLA_G_PER_MM3


def build_coupon(printer: Printer, out: Path) -> Path:
    from boresight_case.export import write_mesh

    d = out / "coupon"
    d.mkdir(parents=True, exist_ok=True)
    for p in coupon_parts():
        write_mesh(p.oriented(), d / p.name)
    (d / "README.md").write_text(
        __doc__.strip() + f"\n\nCurrent setting: clearance {printer.clearance:g} mm, "
        f"interference {printer.interference:g} mm.\n"
    )
    return d
