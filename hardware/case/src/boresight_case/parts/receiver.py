"""The receiver: the bone every other bone joins.

A box tube from the rear cap's port (x = -100) to the barrel's (x = 0),
printed standing on its rear end, so its walls rise straight. Both ends
are ports. Underneath: the grip's socket and the bolt across it. Inside:
rails on both walls for the hub, the feedback carrier and the buttons, and
the trigger bolt's nut boss. In the left wall, where a safety would be:
the power switch's slot, the two LEDs' windows and the buttons' holes.
It carries no purchased part.
"""

from __future__ import annotations

from functools import cache

from build123d import Part

from boresight_case import layout as L
from boresight_case.geom import X, box, opening, side_profile, teardrop, union
from boresight_case.interfaces import Fit, rails
from boresight_case.joints import (
    GRIP_BOLT,
    GRIP_JOINT,
    REAR_PORT,
    RECEIVER_PORT,
    TRIGGER_BOLT,
)
from boresight_case.model import Module, Printed
from boresight_case.vendor import SLIDE_LEVER, SLIDE_THROW

UP = X  # printed standing on its rear end

GRIP_SOCKET_X = (L.GRIP_TOP.X - L.GRIP_JOINT[0] / 2, L.GRIP_TOP.X + L.GRIP_JOINT[0] / 2)
GRIP_TENON_TOP = L.FLOOR_Z + L.GRIP_JOINT_DEPTH
FRONT_RIB_X = -54.5
WINDOW_Z = (-9.0, 15.0)  # the side windows, between the rails
WINDOW_X = (-76.0, -20.0)


def _grip_socket() -> tuple[Part, Part]:
    """(material to add inside: the two ribs, cut: the floor opening). The
    socket's front face slopes at 45 degrees from the floor's underside to
    the top of the rib inside, so it prints without support and the grip's
    tenon wedges against it."""
    x0, x1 = GRIP_SOCKET_X
    w = L.IN_HALF_W
    rise = GRIP_TENON_TOP - L.FLOOR_IN
    # The rear rib stays out of the rear port: low, with its 45-degree back.
    low = x0 - L.RECEIVER_RUN[0]
    rear = side_profile(
        [(x0 - low, L.FLOOR_IN), (x0, L.FLOOR_IN), (x0, L.FLOOR_IN + low)], -w, w
    )
    f_bottom = x1 - L.WALL
    front = side_profile(
        [
            (f_bottom, L.FLOOR_IN),
            (FRONT_RIB_X, L.FLOOR_IN),
            (FRONT_RIB_X, GRIP_TENON_TOP),
            (f_bottom - rise, GRIP_TENON_TOP),
        ],
        -w,
        w,
    )
    cut = side_profile(
        [
            (x0, L.FLOOR_Z - 1),
            (x1 + 1, L.FLOOR_Z - 1),
            (x1, L.FLOOR_Z),
            (f_bottom, L.FLOOR_IN),
            (x0, L.FLOOR_IN),
        ],
        -w,
        w,
    )
    return rear + front, cut


def switch_slot(fit: Fit) -> Part:
    """The slide switch's knob comes out through here, and moves along x."""
    c = fit.clearance
    kx, ky, _ = SLIDE_LEVER
    x, z = L.SWITCH_AT
    half = (kx + SLIDE_THROW) / 2 + 0.5 + c
    return box(
        x - half,
        x + half,
        L.IN_HALF_W - 0.5,
        L.HALF_W + 0.5,
        z - ky / 2 - c - 0.5,
        z + ky / 2 + c + 0.5,
    )


def led_windows() -> Part:
    return union(
        teardrop((x, L.IN_HALF_W - 0.5, z), (0, 1, 0), 1.75, L.WALL + 1, UP)
        for x, z in (L.POWER_LED_AT, L.STATUS_LED_AT)
    )


def button_holes() -> Part:
    return union(
        teardrop((x, L.IN_HALF_W - 0.5, z), (0, 1, 0), 2.2, L.WALL + 1, UP)
        for x, z in L.BUTTON_AT
    )


def side_windows() -> Part:
    """Lightening windows in both walls between the rails, their upper end
    (toward the rear cap in print) a 45-degree gable."""
    x0, x1 = WINDOW_X
    z0, z1 = WINDOW_Z
    height = z1 - z0
    # opening() adds a gable of half the width above `along_up`.
    along = (x1 - x0) - height / 2
    cx = x0 + along / 2
    return union(
        opening(
            (cx, sign * (L.HALF_W - L.WALL / 2), (z0 + z1) / 2),
            (0, sign, 0),
            height,
            along,
            L.WALL + 1,
            UP,
        )
        for sign in (1, -1)
    )


def _trigger_nut_boss(fit: Fit) -> tuple[Part, Part]:
    boss = TRIGGER_BOLT.boss(UP, size=8.0, height=4.5)
    cuts = TRIGGER_BOLT.clear_hole(UP, depth=L.FLOOR_IN - TRIGGER_BOLT.entry[2])
    return boss, cuts + TRIGGER_BOLT.nut_cuts(fit, UP, open_len=4.5)


@cache
def receiver(fit: Fit) -> Module:
    x0, x1 = L.RECEIVER_X
    tube = box(x0, x1, -L.HALF_W, L.HALF_W, -L.HALF_H, L.HALF_H) - box(
        x0 - 1, x1 + 1, -L.IN_HALF_W, L.IN_HALF_W, -L.IN_HALF_H, L.IN_HALF_H
    )
    ribs, socket = _grip_socket()
    boss, boss_cuts = _trigger_nut_boss(fit)
    run = L.RECEIVER_RUN
    body = tube + ribs + boss + REAR_PORT.rib() + RECEIVER_PORT.rib()
    body = body + rails(*run, +1, fit, UP) + rails(*run, -1, fit, UP)
    cuts = [
        socket,
        boss_cuts,
        REAR_PORT.host_cuts(UP),
        RECEIVER_PORT.host_cuts(UP),
        GRIP_BOLT.hole(-L.HALF_W - 1, L.HALF_W + 1, UP),
        switch_slot(fit),
        led_windows(),
        button_holes(),
        side_windows(),
    ]
    shape = body - union(cuts)
    m = Module("receiver")
    m.add(Printed("receiver", shape, UP, "receiver", perimeters=4, infill=30))
    return m


GRIP_JOINT_TUBE = GRIP_JOINT
