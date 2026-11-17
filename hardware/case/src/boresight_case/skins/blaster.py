"""`blaster`: an original faceted sci-fi look. A dorsal fin along the
barrel, a flared muzzle shroud, a trigger guard, a spur over the rear cap
and finger grooves down the grip's front, all faceted at a heavy chamfer.
Its accents (stripes along the barrel, a ring on the muzzle) print as
separate parts in a second filament and press in on pegs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from boresight_case import layout as L
from boresight_case.geom import NEG_X, X, Y, box, cylinder, teardrop, union
from boresight_case.interfaces import SKIN_T, Fit
from boresight_case.keepouts import zones
from boresight_case.skins.base import FLANK, Accent, Style, grip_outline, press_peg

T = SKIN_T
FLARE = 0.3  # the shroud grows this much per mm of length, top and bottom
FIN_X = (12.0, 82.0)
STRIPE = ((15.0, 75.0), (9.0, 15.0), 1.6)  # x range, z range, thickness
STRIPE_PEGS = (25.0, 65.0)
FINGER_S = (52.0, 70.0, 88.0)  # finger grooves down the grip's front
FINGER = (7.0, 2.5)  # radius, depth into the front rim


def _barrel(shroud: float, fin: float) -> list:
    hh = L.HALF_H + T
    x1 = L.BARREL_X[1]
    flare = hh + FLARE * shroud
    outlines = [
        [(L.BARREL_X[0], -hh), (x1, -hh), (x1, hh), (L.BARREL_X[0], hh)],
        [(x1 - 1.0, -hh), (x1 + shroud, -flare), (x1 + shroud, flare), (x1 - 1.0, hh)],
    ]
    if fin > 0:
        f0, f1 = FIN_X
        base = hh - 0.5
        outlines.append(
            [(f0, base), (f1, base), (f1 - fin, base + fin), (f0 + fin, base + fin)]
        )
    return outlines


def _receiver() -> list:
    hh = L.HALF_H + T
    x0, x1 = L.RECEIVER_X
    cx0, cx1 = L.CASSETTE_X
    return [
        [(x0, -hh), (x1, -hh), (x1, hh), (x0, hh)],
        [
            (cx0 - 0.4, L.CASSETTE_Z[0]),
            (cx1 + 0.5, L.CASSETTE_Z[0]),
            (cx1 + 0.5, L.FLOOR_Z + 0.5),
            (cx0 - 0.4, L.FLOOR_Z + 0.5),
        ],
        # The trigger guard: forward from the housing, down, and back under
        # the finger.
        [
            (cx1, -60.0),
            (3.0, -60.0),
            (3.0, -89.0),
            (cx0 - 0.4, -89.0),
            (cx0 - 0.4, -84.0),
            (-2.0, -84.0),
            (-2.0, -65.0),
            (cx1, -65.0),
        ],
        # The spur over the rear cap.
        [(x0, hh - 0.5), (x0 + 18.0, hh - 0.5), (x0 + 11.0, hh + 7.0), (x0, hh + 7.0)],
    ]


def _finger_grooves() -> object:
    r, depth = FINGER
    a = L.GRIP_DEPTH / 2 + T - depth + r
    return union(cylinder(L.grip_point(s, a, -30), Y, r, 60) for s in FINGER_S)


def _accents(shroud: float, fit: Fit) -> list[Accent]:
    (x0, x1), (z0, z1), t = STRIPE
    flank = FLANK["barrel"]
    accents = []
    for side, sign in (("left", 1), ("right", -1)):
        y_face = sign * flank
        plate = box(x0, x1, y_face, y_face + sign * t, z0, z1)
        pegs, holes = [], []
        for px in STRIPE_PEGS:
            peg, hole = press_peg(
                (px, y_face, (z0 + z1) / 2), (0, -sign, 0), SKIN_T - 0.4, fit
            )
            pegs.append(peg)
            holes.append(hole.moved(_loc(0, sign * 2.0, 0)))
        accents.append(
            Accent(f"stripe-{side}", plate + union(pegs), union(holes), (0, sign, 0))
        )
    # The muzzle ring: a frame on the shroud's front face, around the
    # opening the bulkhead slides out through.
    x_front = L.BARREL_X[1] + shroud
    hh = L.HALF_H + T + FLARE * shroud
    frame_outer = box(
        x_front, x_front + 2.0, -flank + 0.6, flank - 0.6, -hh + 0.6, hh - 0.6
    )
    # Its opening: the bulkhead's way out, widened wherever a camera sees.
    ring = frame_outer - union(zones().values())
    pegs, holes = [], []
    # In the shroud's top and bottom rims, where the camera's narrower
    # vertical view never reaches.
    pz_rim = hh - 1.6
    for py in (10.0, -10.0):
        for pz in (pz_rim, -pz_rim):
            peg, _ = press_peg((x_front, py, pz), NEG_X, 3.0, fit)
            pegs.append(peg)
            # The skins print flank down, so these sideways holes come to a
            # 45-degree point toward each half's print direction.
            up = (0, -1, 0) if py > 0 else (0, 1, 0)
            holes.append(teardrop((x_front + 2.0, py, pz), NEG_X, 1.5, 7.0, up))
    accents.append(Accent("muzzle-ring", ring + union(pegs), union(holes), NEG_X))
    return accents


def _loc(dx: float, dy: float, dz: float):
    from build123d import Location

    return Location((dx, dy, dz))


def style(params: Mapping[str, Any], fit: Fit) -> Style:
    shroud = params["shroud_length"]
    out = Style(
        outlines={
            "barrel": _barrel(shroud, params["fin_height"]),
            "receiver": _receiver(),
            "grip": [grip_outline()],
        },
        chamfer=params["chamfer"],
        removals={"grip": _finger_grooves()},
    )
    if params["accents"]:
        out.accents = _accents(shroud, fit)
    return out


__all__ = ["style", "X"]
