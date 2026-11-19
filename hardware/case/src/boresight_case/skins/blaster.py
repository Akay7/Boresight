"""`blaster`: an original faceted sci-fi look. A dorsal fin along each
barrel, a flared shroud on the muzzle ring, a spur over the rear cap and
finger grooves down the grip's front, all faceted at a heavy chamfer. Its
accents, a stripe down each side of the receiver, print separately in a
second filament and are trapped between the covers and the receiver."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from boresight_case import layout as L
from boresight_case.geom import Y, cylinder, union
from boresight_case.interfaces import Fit
from boresight_case.skins.base import SKIN_T, Style, window_accent
from boresight_case.skins.minimal import grip_shapes, rect

T = SKIN_T
FLARE = 0.3  # the shroud grows this much per mm of length, top and bottom
FIN_X = (12.0, 82.0)
STRIPE = ((-62.0, -24.0), (9.0, 15.0))  # x and z of the receiver's stripes
FINGER_S = (52.0, 70.0, 88.0)  # finger grooves down the grip's front
FINGER = (7.0, 2.5)  # radius, depth into the front rim


def _barrel(fin: float) -> list:
    hh = L.HALF_H + T
    outlines = [rect(-10.0, 100.0, -hh, hh)]
    if fin > 0:
        f0, f1 = FIN_X
        base = hh - 0.5
        outlines.append(
            [(f0, base), (f1, base), (f1 - fin, base + fin), (f0 + fin, base + fin)]
        )
    return outlines


def _muzzle(shroud: float) -> list:
    hh = L.HALF_H + T
    x1 = 100.0
    flare = hh + FLARE * shroud
    return [
        rect(90.0, x1, -hh, hh),
        [(x1 - 1.0, -hh), (x1 + shroud, -flare), (x1 + shroud, flare), (x1 - 1.0, hh)],
    ]


def _receiver() -> list:
    hh = L.HALF_H + T
    x0, x1 = L.RECEIVER_X
    return [
        rect(x0, x1, -hh, hh),
        # The spur over the rear cap.
        [(x0, hh - 0.5), (x0 + 18.0, hh - 0.5), (x0 + 11.0, hh + 7.0), (x0, hh + 7.0)],
    ]


def _finger_grooves() -> object:
    r, depth = FINGER
    a = L.GRIP_DEPTH / 2 + T - depth + r
    return union(cylinder(L.grip_point(s, a, -30), Y, r, 60) for s in FINGER_S)


def style(params: Mapping[str, Any], fit: Fit) -> Style:
    shroud = params["shroud_length"]
    out = Style(
        outlines={
            "barrel": _barrel(params["fin_height"]),
            "receiver": _receiver(),
            "grip": grip_shapes(),
            "muzzle": _muzzle(shroud),
        },
        chamfer=params["chamfer"],
        removals={"grip": _finger_grooves()},
    )
    if params["accents"]:
        x, z = STRIPE
        out.accents = [
            window_accent(f"stripe-{side}", "receiver", side, x, z, fit)
            for side in ("left", "right")
        ]
    return out
