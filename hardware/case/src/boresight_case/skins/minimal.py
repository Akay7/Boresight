"""`minimal`: flat panels a cover's thickness off the core, the quickest to
print. An optional shroud past the muzzle, and shallow grooves across the
grip's flanks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from boresight_case import layout as L
from boresight_case.interfaces import Fit
from boresight_case.parts.grip import grip_box
from boresight_case.skins.base import FLANK, SKIN_T, Style, grip_band_x, grip_outline

T = SKIN_T
GROOVE = (1.2, 0.6)  # width, depth
GROOVE_S = (34.0, 80.0, 5.0)  # from, to, pitch down the grip


def _grooves(side: str):
    from boresight_case.geom import union

    flank = FLANK["grip"]
    y0, y1 = (
        (flank - GROOVE[1], flank + 1.0)
        if side == "left"
        else (-flank - 1.0, -flank + GROOVE[1])
    )
    a = L.GRIP_DEPTH / 2 + T + 1.0
    s0, s1, pitch = GROOVE_S
    count = int((s1 - s0) / pitch) + 1
    return union(
        grip_box(-a, a, y0, y1, s0 + k * pitch, s0 + k * pitch + GROOVE[0])
        for k in range(count)
    )


def rect(x0: float, x1: float, z0: float, z1: float) -> list[tuple[float, float]]:
    return [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]


def grip_shapes() -> list[list[tuple[float, float]]]:
    """The grip, its backstrap boss and the band up the receiver's flank."""
    back = L.grip_point(L.BACK_BOSS_S[0], L.BACK_BOSS_A[0] - T)
    low = L.grip_point(L.GRIP_LENGTH - 0.1, L.BACK_BOSS_A[0] - T)
    top_back = L.grip_point(L.BACK_BOSS_S[0] - 8.0, -L.GRIP_DEPTH / 2)
    base_back = L.grip_point(L.GRIP_LENGTH - 0.1, -L.GRIP_DEPTH / 2)
    boss = [
        (top_back.X, top_back.Z),
        (back.X, back.Z),
        (low.X, low.Z),
        (base_back.X, base_back.Z),
    ]
    bx0, bx1 = grip_band_x()
    band = rect(bx0, bx1, L.FLOOR_Z - 4.0, L.GRIP_BOLT[1] + 5.0)
    return [grip_outline(), boss, band]


def style(params: Mapping[str, Any], fit: Fit) -> Style:
    shroud = params["shroud_length"]
    hh = L.HALF_H + T
    out = Style(
        outlines={
            "receiver": [rect(L.RECEIVER_X[0], 0.0, -hh, hh)],
            "barrel": [rect(-10.0, 100.0, -hh, hh)],
            "grip": grip_shapes(),
            "muzzle": [rect(90.0, 100.0 + max(3.0, shroud), -hh, hh)],
        },
        chamfer=params["chamfer"],
    )
    if params["grip_texture"] == "grooves":
        out.flank_cuts["grip"] = _grooves
    return out
