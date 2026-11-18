"""The push-button trigger: no lever, the finger presses the switch
straight back.

    top plate
    |  switch, on the shared plate turned round  <- head ]
    |                                                     | plunger
    |  spring wall: the return spring, the stop screw  <- ] <- finger

The plunger is a paddle the finger presses straight back. Its head, at the
top, presses the switch behind it on the line the lever's tail used, so
the button moves exactly as far as the switch does. A tongue forward along
its top slides between the top plate and a guide bolt across the
housing. The return spring pushes its back from the spring wall. The stop
is an M3 screw in a lock nut in the spring wall: its head stands proud of
the wall, and a pad beside the plunger meets it. A hex key through the
hole in the pad sets it.

The housing prints upside down on its top plate, the plunger flat.
"""

from __future__ import annotations

from build123d import Location, Part, Plane

from boresight_case import layout as L
from boresight_case.geom import (
    X,
    Y,
    box,
    hex_location,
    side_profile,
    teardrop,
    union,
)
from boresight_case.interfaces import Fit
from boresight_case.model import PETG, Module, Printed, bought
from boresight_case.parts.trigger import (
    CONTACT_Z,
    HOUSING_UP,
    INNER,
    MODULE,
    MX_FACE_X,
    SEAT_T,
    SPRING_Z,
    TOP,
    P,
    _bolt_cuts,
    _spring_seat,
    add_mount,
    add_switch,
    bolt_across,
    bolt_bosses,
    bolt_way,
    shared_body,
)
from boresight_case.vendor import (
    M3_CLEAR,
    M3_HEAD_H,
    M3_NUT_AF,
    M3_NYLOC_H,
    MX_STEM_TOP,
)

PLUNGER_UP = Y  # printed on its -y side
HEAD_X = -41.0  # the plunger head's back face, at rest: the switch's contact line
FRONT_X = -37.5  # the paddle's front face, where the finger presses
PLATE_DX = (HEAD_X - MX_STEM_TOP) - MX_FACE_X  # the plate, moved back
HALF = 3.0  # the plunger's half width
PADDLE_BOTTOM = P.Z - 26.0
TONGUE_X = (HEAD_X, -22.0)  # along the top, under the top plate
TONGUE_Z = (TOP - 4.75, TOP - 0.25)
GUIDE = (-29.0, TONGUE_Z[0] - 2.0)  # x, z of the guide bolt under the tongue
SPRING_BOSS = 3.5  # the spring's seat on the plunger's back
STOP_AT = (6.0, P.Z - 10.0)  # y, z of the stop screw
WALL_FACE = L.SPRING_WALL_X[1]
NUT_X = WALL_FACE + 0.5 - M3_NYLOC_H / 2  # the stop's lock nut


def stop_head_x(stop_travel: float) -> float:
    """Where the stop screw's head's top sits for the plunger's pad to meet
    it after `stop_travel`."""
    return HEAD_X - stop_travel


def plunger_shape(travel: float = 0.0) -> Part:
    """The plunger, `travel` mm pressed: the paddle, its head at the top
    on the switch's line, and the tongue forward along the top."""
    paddle = side_profile(
        [
            (HEAD_X, TONGUE_Z[1]),
            (FRONT_X, TONGUE_Z[1]),
            (FRONT_X, P.Z - 8.0),
            (FRONT_X + 1.5, P.Z - 18.0),
            (FRONT_X, PADDLE_BOTTOM),
            (HEAD_X, PADDLE_BOTTOM),
        ],
        -HALF,
        HALF,
    )
    tongue = box(TONGUE_X[0], TONGUE_X[1], -HALF, HALF, *TONGUE_Z)
    # Square, and pointed underneath, so they print lying on the paddle's side.
    seat = box(
        HEAD_X - SPRING_BOSS, HEAD_X + 0.01, -HALF, HALF, SPRING_Z - 3.0, SPRING_Z + 3.0
    )
    spigot = teardrop(
        (HEAD_X - SPRING_BOSS + 0.01, 0, SPRING_Z), (-1, 0, 0), 1.75, 3.0, (0, -1, 0)
    )
    y, z = STOP_AT
    # A pad beside the paddle that the stop screw's head meets, and the hex
    # key's way through it.
    pad = box(HEAD_X, FRONT_X, HALF - 0.01, y + 3.5, z - 3.5, z + 3.5)
    key = teardrop((FRONT_X + 1, y, z), (-1, 0, 0), 1.6, 10.0, Y)
    body = paddle + tongue + seat + spigot + pad - key
    return Location((-travel, 0, 0)) * body


def button_sweep(trigger: str, steps: int = 4) -> Part:
    """The plunger at every point from rest to the stop."""
    end = L.STOP_TRAVEL[trigger]
    return union(plunger_shape(end * k / steps) for k in range(steps + 1))


def _body(fit: Fit) -> Part:
    c = fit.clearance
    gx, gz = GUIDE
    body = shared_body(fit, PLATE_DX) + bolt_bosses(gx, gz) + _spring_seat()
    body = body + _stop_boss()
    # Room behind the plate for the switch's body and pins, in the rear part.
    rear = box(HEAD_X - 22.5, WALL_FACE + 0.01, -9.0, 9.0, CONTACT_Z - 8.5, TOP + 0.01)
    # The microswitch's pins pass back through the spring wall.
    pins = box(
        L.SPRING_WALL_X[0] - 0.5,
        WALL_FACE + 0.01,
        -1.5,
        1.5,
        CONTACT_Z - 21.0,
        CONTACT_Z - 8.0,
    )
    y, z = STOP_AT
    r = M3_NUT_AF / 3**0.5
    cuts = [
        rear,
        pins,
        *_bolt_cuts(fit, gx, gz),
        bolt_way(),
        # The stop screw through the wall, and its lock nut's slot from
        # below, flats to the sides.
        teardrop((WALL_FACE + 0.5, y, z), (-1, 0, 0), M3_CLEAR / 2, 9.0, HOUSING_UP),
        box(
            NUT_X - M3_NYLOC_H / 2 - c,
            NUT_X + M3_NYLOC_H / 2 + c,
            y - M3_NUT_AF / 2 - c,
            y + M3_NUT_AF / 2 + c,
            L.TRIGGER_Z[0] - 0.5,
            z + r + c,
        ),
    ]
    return body - union(cuts)


def _stop_boss() -> Part:
    """The spring wall thickened round the stop screw's lock nut, back to
    just short of the grip's front."""
    y, z = STOP_AT
    top = z + 6.0
    back = max(L.grip_front_x(top) + 0.5, L.SPRING_WALL_X[0] - 2.0)
    return box(back, WALL_FACE + 0.6, 2.6, INNER + 0.01, L.TRIGGER_Z[0], top)


def button_module(fit: Fit, trigger: str) -> Module:
    m = Module(MODULE)
    m.add(
        Printed(
            "trigger-housing-button",
            _body(fit),
            HOUSING_UP,
            MODULE,
            material=PETG,
            perimeters=4,
            infill=40,
        )
    )
    m.add(
        Printed(
            "button-plunger",
            plunger_shape(),
            PLUNGER_UP,
            MODULE,
            material=PETG,
            perimeters=4,
            infill=60,
        )
    )
    add_switch(
        m,
        fit,
        trigger,
        "button-plunger",
        facing=+1,
        contact_x=HEAD_X,
        plate_dx=PLATE_DX,
    )
    add_mount(m, fit)
    bolt_across(m, *GUIDE, "guide bolt", "trigger-housing-button")
    y, z = STOP_AT
    head = stop_head_x(L.STOP_TRAVEL[trigger]) - M3_HEAD_H
    m.add(
        bought(
            "m3x12",
            Location(Plane(origin=(head, y, z), z_dir=(1, 0, 0))),
            "stop screw",
            MODULE,
        )
    )
    m.add(
        bought(
            "m3-nyloc",
            hex_location((NUT_X, y, z), X, (0, 0, -1)),
            "lock nut, stop screw",
            MODULE,
        )
    )
    m.fit("stop screw", "lock nut, stop screw")  # its nylon ring grips the thread
    m.fit("trigger-housing-button", "lock nut, stop screw")
    m.add(
        bought(
            "spring",
            Location((WALL_FACE + SEAT_T, 0, SPRING_Z)),
            "return spring",
            MODULE,
        )
    )
    m.fit("trigger-housing-button", "return spring")
    m.fit("button-plunger", "return spring")
    return m


__all__ = ["button_module", "button_sweep", "SPRING_Z"]
