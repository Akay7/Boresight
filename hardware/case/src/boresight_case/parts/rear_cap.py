"""The rear cap: closes the receiver's back and keeps the Pi's sled in its
rails. It carries the power switch (a snap-in rocker in its back face,
under the thumb) and the regulator for the battery and ESP32-CAM builds,
and the Pi kit's status LED.

Printed on its back face. Its tenon is hollow, so with the cap off the Pi's
micro-SD card slides straight out of the back of the receiver; the switch
and regulator sit clear of that path.
"""

from __future__ import annotations

from functools import cache

from build123d import Location, Plane

from boresight_case import layout as L
from boresight_case.geom import X, box, cylinder, union
from boresight_case.interfaces import Fit
from boresight_case.joints import REAR_CAP_JOINT
from boresight_case.model import Module, Printed, bought
from boresight_case.vendor import ROCKER_CUTOUT

UP = X  # printed on its back face
LED_AT = (L.REAR_CAP_PLATE[0], 10.0, 15.0)  # the LED's centre on the back face
ROCKER_AT = (-3.0, 15.0)  # y, z of the switch on the back face
ROCKER_PANEL = 2.0  # the rocker's clips need a panel this thin
# The regulator stands on its edge in the tenon: its PCB's back face at x,
# 13 mm across y from REG_Y, 21 mm tall from the tenon's floor.
REG_X = -99.0
REG_Y = (-4.0, 9.0)
REG_Z = (-19.5, 1.5)


@cache
def rear_cap(fit: Fit) -> Module:
    x0, x1 = L.REAR_CAP_PLATE
    plate = box(x0, x1, -L.HALF_W, L.HALF_W, -L.HALF_H, L.HALF_H)
    tenon = REAR_CAP_JOINT.tenon(fit, UP)
    # The LED's dome through the plate, its flange in a counterbore inside.
    led_hole = cylinder((x0 - 0.5, LED_AT[1], LED_AT[2]), X, 2.6, x1 - x0 + 1)
    led_flange = cylinder((x1 - 1.2, LED_AT[1], LED_AT[2]), X, 3.1, 1.3)
    shape = plate + tenon + _regulator_rails(fit)
    shape = shape - union(
        [REAR_CAP_JOINT.tenon_cuts(fit, UP), led_hole, led_flange, _rocker_cut(fit)]
    )

    m = Module("rear-cap")
    m.add(Printed("rear-cap", shape, UP, "rear-cap", perimeters=4, infill=25))
    if fit.fastener == "insert":
        m.add(
            bought(
                "m3-insert",
                REAR_CAP_JOINT.insert_location(fit),
                "insert, rear cap joint",
                "rear-cap",
            )
        )
    else:
        m.add(
            bought(
                "m3-nut",
                REAR_CAP_JOINT.nut_location(fit, UP),
                "nut, rear cap joint",
                "rear-cap",
            )
        )
    m.fit("rear-cap", m.bought[-1].label)
    return m


def _rocker_cut(fit: Fit):
    """The rocker's cut-out through a 2 mm panel, with room for its body and
    clips behind it."""
    c = fit.clearance
    y, z = ROCKER_AT
    cw, ch = ROCKER_CUTOUT  # 13 across y, 9 along z
    x0, x1 = L.REAR_CAP_PLATE
    hole = box(
        x0 - 0.5,
        x1 + 0.5,
        y - cw / 2 - c,
        y + cw / 2 + c,
        z - ch / 2 - c,
        z + ch / 2 + c,
    )
    behind = box(
        x0 + ROCKER_PANEL,
        x1 + 0.5,
        y - cw / 2 - 1.5,
        y + cw / 2 + 1.5,
        z - ch / 2 - 1.5,
        z + ch / 2 + 1.5,
    )
    return hole + behind


def _regulator_rails(fit: Fit):
    """Two slotted rails on the plate's inside that the regulator slides
    down into, edge first."""
    c = fit.clearance
    y0, y1 = REG_Y
    z0, z1 = REG_Z
    x0 = L.REAR_CAP_PLATE[1]
    rails = []
    for edge, outward in ((y0, -1), (y1, 1)):
        ya, yb = sorted((edge - outward * 0.9, edge + outward * (c + 2.0)))
        rail = box(x0, REG_X + 1.6 + 3.0, ya, yb, z0 - 0.25, z1)
        sa, sb = sorted((edge - outward * 1.0, edge + outward * c))
        slot = box(REG_X - c, REG_X + 1.6 + c, sa, sb, z0 - 1, z1 + 1)
        rails.append(rail - slot)
    return union(rails)


def power_parts(module: str = "rear-cap") -> list:
    """The switch and regulator of a battery or ESP32-CAM tether build."""
    y, z = ROCKER_AT
    rocker = Location(
        Plane(origin=(L.REAR_CAP_PLATE[0], y, z), x_dir=(0, 1, 0), z_dir=(-1, 0, 0))
    )
    reg = Location(
        Plane(
            origin=(REG_X, (REG_Y[0] + REG_Y[1]) / 2, (REG_Z[0] + REG_Z[1]) / 2),
            x_dir=(0, 0, 1),
            z_dir=(1, 0, 0),
        )
    )
    return [
        bought("rocker", rocker, "power switch", module),
        bought("buck-boost", reg, "regulator", module),
    ]


def led(module: str = "rear-cap"):
    """The Pi kit's status LED in the rear cap, dome facing backward."""
    where = Location(
        Plane(origin=(L.REAR_CAP_PLATE[1], LED_AT[1], LED_AT[2]), z_dir=(-1, 0, 0))
    )
    return bought("led5", where, "status LED", module)
