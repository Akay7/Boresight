"""The rear cap: closes the receiver's back and holds the carriers in its
rails. A plate and the standard tenon, 12 mm into the receiver's rear port,
held by the port's two through-bolts. It holds nothing electrical.

Printed on its back face.
"""

from __future__ import annotations

from functools import cache

from boresight_case import layout as L
from boresight_case.geom import X, box
from boresight_case.interfaces import Fit
from boresight_case.joints import REAR_PORT
from boresight_case.model import Module, Printed

UP = X  # printed on its back face


@cache
def rear_cap(fit: Fit) -> Module:
    x0, x1 = L.REAR_CAP_PLATE
    plate = box(x0, x1, -L.HALF_W, L.HALF_W, -L.HALF_H, L.HALF_H)
    shape = plate + REAR_PORT.tenon(fit, UP)
    m = Module("rear-cap")
    m.add(Printed("rear-cap", shape, UP, "rear-cap", perimeters=4, infill=25))
    return m
