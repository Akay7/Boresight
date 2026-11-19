"""The barrel: a box tube, the same part however many a gun has.

Printed standing on its muzzle end, so the tenon at its rear rises from
the top. The tenon goes into whichever port is behind it (the receiver's,
or another barrel's muzzle port); its muzzle end is a port in turn. Rails
on both walls take carriers; a window in the floor lets the Pi's cables
plug in from below, with ribs along its edges; windows in both side walls
lighten it, and the right one is the vent over the Pi's processor. It
carries no purchased part.

Built in the first barrel's place (x 0 to 100); a gun moves copies along.
"""

from __future__ import annotations

from functools import cache

from build123d import Part

from boresight_case import layout as L
from boresight_case.geom import NEG_X, box, opening, union
from boresight_case.interfaces import Fit, rails
from boresight_case.joints import CLAMP_FIX, RECEIVER_PORT, barrel_port
from boresight_case.model import Module, Printed

UP = NEG_X  # printed standing on the muzzle
TENON_PORT = RECEIVER_PORT  # the first barrel's tenon fills the receiver's port
MUZZLE_PORT = barrel_port(0)
WINDOW_RIB = (2.0, 2.5)  # width, height above the floor's inside
SIDE_WINDOW_Z = (-9.0, 15.0)
SIDE_WINDOW_X = (14.0, 80.0)
CLAMP_X, CLAMP_Y = CLAMP_FIX.entry[:2]  # the cable clamp's thumbscrew


def window() -> Part:
    """The window in the floor, its rear end (the top in print) gabled at
    45 degrees."""
    x0, x1 = L.WINDOW_X
    y0, y1 = L.WINDOW_Y
    across = y1 - y0
    along = (x1 - x0) - across / 2
    return opening(
        (x1 - along / 2, (y0 + y1) / 2, L.FLOOR_Z + L.WALL / 2),
        (0, 0, 1),
        across,
        along,
        L.WALL + 1,
        UP,
    )


def window_ribs() -> Part:
    """Ribs along the window's two long edges, inside the floor."""
    x0, x1 = L.WINDOW_X
    w, h = WINDOW_RIB
    y0, y1 = L.WINDOW_Y
    z = L.FLOOR_IN
    return union(
        box(x0, x1 + 2.0, y, y + side * w, z - 0.01, z + h)
        for y, side in ((y0, -1), (y1, 1))
    )


def vents() -> Part:
    """The vents over the Pi's processor: the right wall's side window, which
    faces the heatsink."""
    return side_windows(sides=(-1,))


def side_windows(sides: tuple[int, ...] = (1, -1)) -> Part:
    """Lightening windows in both walls between the rails, their rear end
    (the top in print) gabled."""
    x0, x1 = SIDE_WINDOW_X
    z0, z1 = SIDE_WINDOW_Z
    height = z1 - z0
    along = (x1 - x0) - height / 2
    cx = x1 - along / 2
    return union(
        opening(
            (cx, sign * (L.HALF_W - L.WALL / 2), (z0 + z1) / 2),
            (0, sign, 0),
            height,
            along,
            L.WALL + 1,
            UP,
        )
        for sign in sides
    )


def clamp_hole() -> Part:
    """The cable clamp's thumbscrew: up through the floor just ahead of the
    window, into a nut in a boss on the floor's inside."""
    from boresight_case.geom import teardrop

    return teardrop((CLAMP_X, CLAMP_Y, L.FLOOR_Z - 1), (0, 0, 1), 1.7, L.WALL + 2, UP)


@cache
def barrel(fit: Fit) -> Module:
    x0, x1 = L.barrel_x(0)
    tube = box(x0, x1, -L.HALF_W, L.HALF_W, -L.HALF_H, L.HALF_H) - box(
        x0 - 1, x1 + 1, -L.IN_HALF_W, L.IN_HALF_W, -L.IN_HALF_H, L.IN_HALF_H
    )
    run = L.BARREL_RUN
    body = tube + TENON_PORT.tenon(fit, UP) + MUZZLE_PORT.rib() + window_ribs()
    body = body + rails(*run, +1, fit, UP) + rails(*run, -1, fit, UP)
    body = body + CLAMP_FIX.boss(UP, size=8.0, height=3.5)
    cuts = [
        CLAMP_FIX.nut_cuts(fit, UP, open_len=3.5),
        MUZZLE_PORT.host_cuts(UP),
        window(),
        side_windows(),
        clamp_hole(),
    ]
    shape = body - union(cuts)
    m = Module("barrel")
    m.add(Printed("barrel", shape, UP, "barrel", perimeters=4, infill=25))
    return m
