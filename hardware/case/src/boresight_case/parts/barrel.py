"""The barrel: a box tube from the receiver to the muzzle.

Printed standing on its muzzle end, so the tenon that enters the receiver
rises from the top. The camera bulkhead slides into the muzzle end, keyed
by a rib under the top wall, and is held by one screw from below.
"""

from __future__ import annotations

from functools import cache

from boresight_case import layout as L
from boresight_case.geom import NEG_X, box, teardrop, union
from boresight_case.interfaces import Fit
from boresight_case.joints import (
    ATTACHMENTS,
    BARREL_JOINT,
    BULKHEAD_SCREW,
    BULKHEAD_SLIDE,
)
from boresight_case.model import Module, Printed, bought

UP = NEG_X  # printed standing on the muzzle
LIGHT_GUIDE = (88.2, 7.5)  # x, y of the ESP32-CAM's status light guide


@cache
def barrel(fit: Fit) -> Module:
    x0, x1 = L.BARREL_X
    tube = box(x0, x1, -L.HALF_W, L.HALF_W, -L.HALF_H, L.HALF_H) - box(
        x0 - 1, x1 + 1, -L.IN_HALF_W, L.IN_HALF_W, -L.IN_HALF_H, L.IN_HALF_H
    )
    tenon = BARREL_JOINT.tenon(fit, UP)
    bosses = union(ATTACHMENTS[("barrel", s)].core_boss(UP) for s in ("left", "right"))
    shape = tube + tenon + BULKHEAD_SLIDE.rib() + bosses
    cuts = [
        BARREL_JOINT.tenon_cuts(fit, UP),
        BULKHEAD_SCREW.clear_hole(UP, depth=L.WALL),
        # The light guide's window, over the ESP32-CAM's status LED.
        teardrop(
            (LIGHT_GUIDE[0], LIGHT_GUIDE[1], L.IN_HALF_H - 0.5),
            (0, 0, 1),
            1.1,
            L.WALL + 1,
            UP,
        ),
    ]
    cuts += [ATTACHMENTS[("barrel", s)].core_cuts(fit, UP) for s in ("left", "right")]
    shape = shape - union(cuts)

    m = Module("barrel")
    m.add(Printed("barrel", shape, UP, "barrel", perimeters=4, infill=25))
    if fit.fastener == "insert":
        m.add(
            bought(
                "m3-insert",
                BARREL_JOINT.insert_location(fit),
                "insert, barrel joint",
                "barrel",
            )
        )
    else:
        m.add(
            bought(
                "m3-nut",
                BARREL_JOINT.nut_location(fit, UP),
                "nut, barrel joint",
                "barrel",
            )
        )
    m.fit("barrel", m.bought[-1].label)
    for side in ("left", "right"):
        a = ATTACHMENTS[("barrel", side)]
        if fit.fastener == "insert":
            m.add(
                bought(
                    "m3-insert",
                    a.insert_location(),
                    f"insert, barrel skin {side}",
                    "barrel",
                )
            )
        else:
            m.add(
                bought(
                    "m3-nut", a.nut_location(UP), f"nut, barrel skin {side}", "barrel"
                )
            )
        m.fit("barrel", m.bought[-1].label)
    return m
