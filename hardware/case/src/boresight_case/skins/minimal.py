"""`minimal`: flat panels a skin's thickness off the core, the quickest to
print. An optional shroud past the muzzle, and shallow grooves across the
grip's flanks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from boresight_case import layout as L
from boresight_case.interfaces import SKIN_T, Fit
from boresight_case.parts.grip import grip_box
from boresight_case.skins.base import FLANK, Style, grip_outline

T = SKIN_T
GROOVE = (1.2, 0.6)  # width, depth
GROOVE_S = (34.0, 108.0, 5.0)  # from, to, pitch down the grip


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


def style(params: Mapping[str, Any], fit: Fit) -> Style:
    shroud = params["shroud_length"]
    hh = L.HALF_H + T
    barrel = [
        [
            (L.BARREL_X[0], -hh),
            (L.BARREL_X[1] + shroud, -hh),
            (L.BARREL_X[1] + shroud, hh),
            (L.BARREL_X[0], hh),
        ]
    ]
    receiver = [
        [
            (L.RECEIVER_X[0], -hh),
            (L.RECEIVER_X[1], -hh),
            (L.RECEIVER_X[1], hh),
            (L.RECEIVER_X[0], hh),
        ],
        # The trigger housing: plates over the cassette's flanks.
        [
            (L.CASSETTE_X[0] - 0.4, L.CASSETTE_Z[0]),
            (L.CASSETTE_X[1] + 0.5, L.CASSETTE_Z[0]),
            (L.CASSETTE_X[1] + 0.5, L.FLOOR_Z + 0.5),
            (L.CASSETTE_X[0] - 0.4, L.FLOOR_Z + 0.5),
        ],
    ]
    out = Style(
        outlines={"barrel": barrel, "receiver": receiver, "grip": [grip_outline()]},
        chamfer=params["chamfer"],
    )
    if params["grip_texture"] == "grooves":
        out.flank_cuts["grip"] = _grooves
    return out
