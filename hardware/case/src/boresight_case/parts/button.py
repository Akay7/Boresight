"""The push-button trigger: no lever, the finger presses the switch
straight on.

    top plate
    |  front wall, the guide block below it
    |  [====]--- rod ---[cap]  <- finger
    | head
    |  ^ switch, on the shared plate     ^ stop screw's head in front of
    |  ^ return spring, on the plate       the block, set through the cap

A plunger slides straight back through a guide block under the front
wall. Its head meets the switch where the lever's pad did, so the button
moves as far as the switch does, and the return spring pushes on its
lower half. The plunger sits off centre so the cassette screw's way up
from below stays clear. A cap pressed onto the rod's front end is the
finger pad. The stop is an M3 screw in a lock nut in the guide block: its
head stands proud of the block's front face, and the cap's back meets it.
A hex key through the hole in the cap sets it.

The cassette prints upside down on its top plate, the plunger on its
side, the cap on its face.
"""

from __future__ import annotations

from build123d import Location, Part, Plane

from boresight_case import layout as L
from boresight_case.geom import X, Y, Z, box, cylinder, hex_location, teardrop, union
from boresight_case.interfaces import Fit
from boresight_case.model import PETG, Module, Printed, bought
from boresight_case.parts.trigger import (
    CASSETTE_UP,
    CONTACT_X,
    MODULE,
    SPRING_Z,
    add_switch,
    screw_way,
    shared_body,
)
from boresight_case.vendor import M3_CLEAR, M3_HEAD_H, M3_NUT_AF, M3_NYLOC_H

PLUNGER_UP = Y  # printed on its -y side
CAP_UP = (-1, 0, 0)  # printed on its face

FRONT = L.CASSETTE_X[1]  # the cassette's front face: the stop screw sits in it
HEAD_FRONT = -22.0  # the plunger's head rests against the guide block's back
BLOCK_BOTTOM = -58.0
ROD_Y = (-6.0, 0.5)  # off centre, clear of the cassette screw's way up
ROD_Z = (-55.5, -48.5)
HEAD_Y = (-6.0, 3.25)
HEAD_Z = (-67.0, -48.5)
HEAD_STEP_Z = -58.0  # below it the head steps forward to seat the spring
SPRING_FACE_X = L.SPRING_SEAT_X + 9.0  # the spring's installed length is 9 mm
CAP_X = (-7.0, -2.0)
CAP_Y = (-9.0, 7.0)
CAP_Z = (-60.0, -38.0)
SOCKET = 3.0  # the rod's end in the cap
STOP_AT = (-2.75, -44.0)  # y, z of the stop screw


def stroke_gap(stop_travel: float) -> float:
    """How far the stop screw's head stands off the block's front face for
    the cap to meet it after `stop_travel`: the cap rests 7 mm off the
    face, the head is 3 mm tall."""
    rest_gap = CAP_X[0] - FRONT
    return rest_gap - M3_HEAD_H - stop_travel


def plunger_shape(travel: float = 0.0) -> Part:
    """The plunger, `travel` mm pressed."""
    upper = box(CONTACT_X, HEAD_FRONT, *HEAD_Y, HEAD_STEP_Z, HEAD_Z[1])
    lower = box(SPRING_FACE_X, HEAD_FRONT, *HEAD_Y, HEAD_Z[0], HEAD_STEP_Z + 0.01)
    rod = box(HEAD_FRONT - 0.01, CAP_X[0] + SOCKET, *ROD_Y, *ROD_Z)
    return Location((-travel, 0, 0)) * (upper + lower + rod)


def cap_shape(fit: Fit, travel: float = 0.0) -> Part:
    """The finger pad: a socket the rod presses into, and a hole for the hex
    key to reach the stop screw."""
    pad = box(*CAP_X, *CAP_Y, *CAP_Z)
    i = fit.interference
    socket = box(
        CAP_X[0] - 0.01,
        CAP_X[0] + SOCKET,
        ROD_Y[0] + i,
        ROD_Y[1] - i,
        ROD_Z[0] + i,
        ROD_Z[1] - i,
    )
    key = cylinder((CAP_X[0] - 1, *STOP_AT), X, 1.6, CAP_X[1] - CAP_X[0] + 2)
    return Location((-travel, 0, 0)) * (pad - socket - key)


def button_sweep(trigger: str, fit: Fit | None = None, steps: int = 4) -> Part:
    """The plunger and cap at every point from rest to the stop."""
    fit = fit or Fit()
    end = L.STOP_TRAVEL[trigger]
    return union(
        plunger_shape(end * k / steps) + cap_shape(fit, end * k / steps)
        for k in range(steps + 1)
    )


def _stop_nut_x() -> float:
    return FRONT - 3.0 - M3_NYLOC_H / 2


def _body(fit: Fit) -> Part:
    c = fit.clearance
    w, t = L.CASSETTE_HALF_W, L.CASSETTE_WALL
    body = shared_body(fit, front_bottom=BLOCK_BOTTOM)
    # The guide block: back to the plunger's head, up to the top plate, so
    # nothing in it overhangs as it prints.
    block = box(
        HEAD_FRONT,
        L.FRONT_WALL_X[0] + 0.01,
        -w + t,
        w - t,
        BLOCK_BOTTOM,
        L.FLOOR_Z - 0.01,
    )
    y, z = STOP_AT
    r = M3_NUT_AF / 3**0.5
    nx = _stop_nut_x()
    cuts = [
        # The plunger's guide.
        box(
            HEAD_FRONT - 0.5,
            FRONT + 0.5,
            ROD_Y[0] - c,
            ROD_Y[1] + c,
            ROD_Z[0] - c,
            ROD_Z[1] + c,
        ),
        # The stop screw, clear through the block.
        teardrop(
            (FRONT + 0.5, y, z),
            (-1, 0, 0),
            M3_CLEAR / 2,
            FRONT - HEAD_FRONT + 1.0,
            CASSETTE_UP,
        ),
        # Its lock nut slides in through the right wall, flats up and down.
        box(
            nx - M3_NYLOC_H / 2 - c,
            nx + M3_NYLOC_H / 2 + c,
            -w - 0.5,
            y + r + c,
            z - M3_NUT_AF / 2 - c,
            z + M3_NUT_AF / 2 + c,
        ),
        screw_way(BLOCK_BOTTOM),
    ]
    return body + block - union(cuts)


def button_module(fit: Fit, trigger: str) -> Module:
    m = Module(MODULE)
    m.add(
        Printed(
            "button-cassette",
            _body(fit),
            CASSETTE_UP,
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
    m.add(
        Printed(
            "button-cap",
            cap_shape(fit),
            CAP_UP,
            MODULE,
            material=PETG,
            perimeters=3,
            infill=40,
        )
    )
    m.fit("button-plunger", "button-cap")  # the rod is pressed into the cap
    add_switch(m, fit, trigger, "button-plunger")
    y, z = STOP_AT
    head = FRONT + stroke_gap(L.STOP_TRAVEL[trigger])
    m.add(
        bought(
            "m3x12", Location(Plane(origin=(head, y, z), z_dir=X)), "stop screw", MODULE
        )
    )
    m.add(
        bought(
            "m3-nyloc",
            hex_location((_stop_nut_x(), y, z), X, Z),
            "lock nut, stop screw",
            MODULE,
        )
    )
    m.fit("stop screw", "lock nut, stop screw")  # its nylon ring grips the thread
    m.fit("button-cassette", "lock nut, stop screw")
    return m


__all__ = ["button_module", "button_sweep", "SPRING_Z"]
