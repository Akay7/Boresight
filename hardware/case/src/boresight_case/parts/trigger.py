"""The trigger: a drop-in cassette under the receiver's floor, in three
mechanisms on one mount (the receiver's rails, one screw, the trigger
plug), all taking the same switch plates.

    top plate (against the receiver's floor)
    |  pivot, on a 1.75 mm filament pin or an M3 bolt
    |  o--- upper arm -> stop screw, in the front wall
    |  |
    |  |pad -> switch (on a swappable plate)
    |  |
    |  |  <- return spring, seated on the plate
    |  )  blade

The lever turns between two bosses. Pulling it swings its pad back onto
the switch: an MX-style switch's stem, or a lever microswitch's tip.
Above the pivot, its upper arm swings forward onto the stop screw, whose
depth sets where the pull ends, past the switch's actuation and short of
its end of travel. A ballpoint-pen spring seated on the switch plate
returns it. The push button (`parts.button`) meets the same switch at the
same place, straight on.

The cassette prints upside down on its top plate; the lever and the plates
print flat.
"""

from __future__ import annotations

import math
from functools import cache

from build123d import Location, Part, Plane

from boresight_case import layout as L
from boresight_case.catalog import MECHANISM_PARTS
from boresight_case.geom import (
    X,
    Y,
    Z,
    box,
    cylinder,
    hex_location,
    hexagon_prism,
    side_profile,
    teardrop,
    union,
)
from boresight_case.interfaces import Fit
from boresight_case.joints import CASSETTE_SCREW
from boresight_case.model import PETG, Module, Printed, bought
from boresight_case.vendor import (
    M3_CLEAR,
    M3_HEAD_CBORE,
    M3_NUT_AF,
    M3_NUT_H,
    M3_NYLOC_H,
    MICRO,
    MICRO_HINGE_X,
    MICRO_HOLE_D,
    MICRO_HOLE_PITCH,
    MICRO_HOLE_Z,
    MICRO_LEVER_FREE,
    MICRO_LEVER_LEN,
    MICRO_OVERTRAVEL,
    MICRO_PRETRAVEL,
    MX_ACTUATION,
    MX_CUTOUT,
    MX_STEM_TOP,
    MX_TRAVEL,
)

CASSETTE_UP = (0, 0, -1)  # printed upside down, on its top plate
LEVER_UP = Y  # printed flat
PLATE_UP = X  # the MX plate prints face up
CARRIER_UP = X  # the microswitch carrier prints face up too
MODULE = "trigger-cassette"

P = L.PIVOT
PAD = 2.5  # the pad's face behind the pivot axis
BACK = 1.0  # the lever's back face elsewhere, recessed so only the pad touches
CONTACT_X = P.X - PAD  # every mechanism meets the switch here, at rest
CONTACT_Z = P.Z - L.CONTACT_R
SPRING_Z = P.Z - L.SPRING_R
STOP_Z = P.Z + L.STOP_R
PIN_D = 1.75
HUB_R = 4.0
BOSS_GAP = 0.25  # each side of the lever, between it and the bosses
PLATE_HALF_Y = L.CASSETTE_HALF_W - L.CASSETTE_WALL + 1.0  # into 1 mm grooves
PLATE_Z = (L.CASSETTE_Z[0] + 1.0, L.FLOOR_Z)  # rests on the grooves' closed ends
MX_FACE_X = CONTACT_X - MX_STEM_TOP  # the MX's plate-top face: its stem on the line
WEB_X = (L.PLATE_X[0], L.PLATE_X[0] + 1.5)  # the 1.5 mm web the MX clips into
JST_AT = (-44.0, -3.0)
SPRING_SEAT = (L.PLATE_X[1], L.SPRING_SEAT_X)

# The bolt mechanism: an M3 x 12 through the hub, its head and nut sunk into
# the bosses so a 12 mm screw spans the 22 mm cassette.
BOLT_BOSS_R = 5.5
BOLT_SEAT = 1.2  # boss left under the head, and under the nut
BOLT_HEAD_Y = L.LEVER_W / 2 + BOSS_GAP + BOLT_SEAT  # the head's underside


# -- the lever's motion -----------------------------------------------------------


def pad_travel(angle: float) -> float:
    """How far the pad's face has moved back along the contact line, at
    `angle` radians of pull."""
    return PAD / math.cos(angle) - PAD + L.CONTACT_R * math.tan(angle)


def angle_for_travel(travel: float) -> float:
    lo, hi = 0.0, math.radians(30)
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if pad_travel(mid) < travel else (lo, mid)
    return (lo + hi) / 2


def stop_tip_x(trigger: str) -> float:
    """Where the stop screw's tip sits so the upper arm meets it at the
    plate's default stop."""
    a = angle_for_travel(L.STOP_TRAVEL[trigger])
    return P.X + PAD / math.cos(a) + L.STOP_R * math.tan(a)


def switch_limits(trigger: str) -> tuple[float, float]:
    """(actuation, end of travel) at the contact, in mm."""
    if trigger == "mx":
        return MX_ACTUATION, MX_TRAVEL
    return MICRO_PRETRAVEL, MICRO_PRETRAVEL + MICRO_OVERTRAVEL


# -- the lever ----------------------------------------------------------------------


def _lever_profile() -> list[tuple[float, float]]:
    x, z = P.X, P.Z
    pts = [
        (-PAD, 6.0),
        (PAD, 6.0),
        (PAD, -30.0),
        (5.0, -35.0),
        (5.0, -39.0),
        (2.0, -42.5),
        (-BACK, -42.0),
        (-BACK, -L.CONTACT_R - 3.0),
        (-PAD, -L.CONTACT_R - 3.0),
        (-PAD, -L.CONTACT_R + 3.0),
        (-BACK, -L.CONTACT_R + 3.0),
        (-BACK, 0.0),
        (-PAD, 0.0),
    ]
    return [(x + dx, z + dz) for dx, dz in pts]


def _hub_bore(mechanism: str) -> float:
    """The lever's hub hole: round the filament pin, or clear of the bolt."""
    return PIN_D / 2 + 0.1 if mechanism == "filament" else M3_CLEAR / 2


def lever_shape(angle: float = 0.0, mechanism: str = "filament") -> Part:
    """The lever, turned `angle` radians toward the pull."""
    half = L.LEVER_W / 2
    body = side_profile(_lever_profile(), -half, half)
    body = body + cylinder((P.X, -half, P.Z), Y, HUB_R, L.LEVER_W)
    body = body - cylinder(
        (P.X, -half - 1, P.Z), Y, _hub_bore(mechanism), L.LEVER_W + 2
    )
    if angle:
        from build123d import Axis

        body = body.rotate(Axis((P.X, 0, P.Z), (0, 1, 0)), math.degrees(angle))
    return body


def lever_sweep(trigger: str, steps: int = 6, mechanism: str = "filament") -> Part:
    """Every position of the lever from rest to the stop."""
    end = angle_for_travel(L.STOP_TRAVEL[trigger])
    return union(lever_shape(end * k / steps, mechanism) for k in range(steps + 1))


# -- what every cassette shares -------------------------------------------------------


def shared_body(fit: Fit, front_bottom: float = L.FRONT_WALL_Z[0]) -> Part:
    """Top plate, side walls and front wall (down to `front_bottom`), with
    the switch plate's seat, the trigger plug's pocket and the cassette
    screw's hole: the mount and the plate seat every mechanism keeps."""
    c = fit.clearance
    x0, x1 = L.CASSETTE_X
    z0, z1 = L.CASSETTE_Z
    w, t = L.CASSETTE_HALF_W, L.CASSETTE_WALL
    top = box(x0, x1, -w, w, z1 - L.CASSETTE_TOP_T, z1)
    walls = box(x0, x1, w - t, w, z0, z1) + box(x0, x1, -w, -w + t, z0, z1)
    front = box(*L.FRONT_WALL_X, -w + t, w - t, front_bottom, L.FRONT_WALL_Z[1])
    cuts = [
        # The switch plate's grooves (closed 1 mm above the bottom, where the
        # plate rests) and its slot through the top plate.
        box(
            L.PLATE_X[0] - c,
            L.PLATE_X[1] + c,
            -PLATE_HALF_Y - c,
            PLATE_HALF_Y + c,
            z0 + 1.0,
            z1 + 0.5,
        ),
        # The trigger plug's pocket through the top plate.
        box(
            JST_AT[0] - 3.2,
            JST_AT[0] + 3.2,
            JST_AT[1] - 3.1,
            JST_AT[1] + 3.1,
            z1 - L.CASSETTE_TOP_T - 0.5,
            z1 + 0.5,
        ),
        screw_way(front_bottom),
    ]
    return top + walls + front - union(cuts)


def screw_way(front_bottom: float = L.FRONT_WALL_Z[0]) -> Part:
    """The cassette screw's hole, and its way up from below for the screw
    and the hex key. Each mechanism cuts it again after adding its own
    parts, so nothing it adds can block it."""
    entry = CASSETTE_SCREW.entry
    wall_bottom = L.FRONT_WALL_Z[0]
    way = CASSETTE_SCREW.clear_hole(
        CASSETTE_UP, depth=L.FLOOR_Z - entry[2] + 0.5
    ) + CASSETTE_SCREW.head_room(depth=entry[2] - wall_bottom + 0.5)
    if front_bottom < wall_bottom:
        # Below the front wall, square: the head and the key pass, and the
        # cut stays robust where it crosses a pivot boss's curved faces.
        half = M3_HEAD_CBORE / 2 + 0.2
        way = way + box(
            entry[0] - half,
            entry[0] + half,
            entry[1] - half,
            entry[1] + half,
            front_bottom - 0.5,
            wall_bottom + 0.01,
        )
    return way


def _lever_body(fit: Fit, mechanism: str) -> Part:
    w, t = L.CASSETTE_HALF_W, L.CASSETTE_WALL
    inner = L.LEVER_W / 2 + BOSS_GAP
    boss_r = HUB_R + 0.5 if mechanism == "filament" else BOLT_BOSS_R
    # Bosses each side of the hub, their undersides (in print) pointed.
    bosses = union(
        teardrop(
            (P.X, sign * (w - t + 0.01), P.Z),
            (0, -sign, 0),
            boss_r,
            w - t - inner,
            Z,
        )
        for sign in (1, -1)
    )
    body = shared_body(fit) + bosses
    cuts = [
        # The stop screw, clear through the front wall into a captive
        # nylon-insert lock nut, which holds it wherever it is set.
        teardrop(
            (L.FRONT_WALL_X[1] + 0.5, 0, STOP_Z),
            (-1, 0, 0),
            M3_CLEAR / 2,
            L.FRONT_WALL_X[1] - L.FRONT_WALL_X[0] + 1.0,
            CASSETTE_UP,
        ),
        _stop_nut_slot(fit),
        # Down past the bosses: the screw's head hangs below the front wall.
        screw_way(P.Z - boss_r - 1.0),
    ]
    if mechanism == "filament":
        cuts.append(
            teardrop((P.X, -w - 0.5, P.Z), Y, PIN_D / 2 + 0.05, 2 * w + 1, CASSETTE_UP)
        )
    else:
        cuts += _bolt_cuts(fit)
    return body - union(cuts)


def _bolt_cuts(fit: Fit) -> list[Part]:
    """The bolt's bore through both bosses, its head's counterbore from the
    left, its nut's pocket from the right: all sideways in print, so the
    round ones come to a point and the nut's has a flat on top."""
    w = L.CASSETTE_HALF_W
    bore = teardrop((P.X, -w - 0.5, P.Z), Y, M3_CLEAR / 2, 2 * w + 1, CASSETTE_UP)
    head = teardrop(
        (P.X, BOLT_HEAD_Y, P.Z),
        Y,
        M3_HEAD_CBORE / 2,
        w - BOLT_HEAD_Y + 0.5,
        CASSETTE_UP,
    )
    nut_len = w - BOLT_HEAD_Y + 0.5
    nut = hexagon_prism(
        (P.X, -BOLT_HEAD_Y - nut_len / 2, P.Z), Y, fit.nut_af, nut_len, CASSETTE_UP
    )
    return [bore, head, nut]


def _stop_nut_slot(fit: Fit) -> Part:
    """A slot from the front wall's underside that the stop screw's nut
    drops into, flats to the sides."""
    c = fit.clearance
    nx = _stop_nut_x()
    r = M3_NUT_AF / math.sqrt(3)
    return box(
        nx - M3_NYLOC_H / 2 - c,
        nx + M3_NYLOC_H / 2 + c,
        -M3_NUT_AF / 2 - c,
        M3_NUT_AF / 2 + c,
        L.FRONT_WALL_Z[0] - 0.5,
        STOP_Z + r + c,
    )


def _stop_nut_x() -> float:
    return (L.FRONT_WALL_X[0] + L.FRONT_WALL_X[1]) / 2


# -- switch plates --------------------------------------------------------------------


def _plate_outline(fit: Fit) -> Part:
    c = fit.clearance
    return box(
        L.PLATE_X[0],
        L.PLATE_X[1],
        -PLATE_HALF_Y + c,
        PLATE_HALF_Y - c,
        PLATE_Z[0] + c,
        PLATE_Z[1] - c,
    )


def _spring_seat(up) -> Part:
    """A boss on the plate's front face and a spigot into the spring."""
    x0, x1 = SPRING_SEAT
    boss = teardrop((x0 - 0.01, 0, SPRING_Z), X, 3.25, x1 - x0 + 0.01, up)
    spigot = teardrop((x1, 0, SPRING_Z), X, 1.75, 3.0, up)
    return boss + spigot


def mx_plate(fit: Fit) -> Part:
    """A 3 mm plate: the 14 mm cut-out through its 1.5 mm back web, and a
    counterbore in front for the switch's housing to sit in."""
    c = fit.clearance
    plate = _plate_outline(fit) + _spring_seat(PLATE_UP)
    cut = box(
        L.PLATE_X[0] - 1,
        L.PLATE_X[1] + 1,
        -MX_CUTOUT / 2,
        MX_CUTOUT / 2,
        CONTACT_Z - MX_CUTOUT / 2,
        CONTACT_Z + MX_CUTOUT / 2,
    )
    pocket = box(
        WEB_X[1],
        L.PLATE_X[1] + 1,
        -8.0 - c,
        8.0 + c,
        CONTACT_Z - 8.0 - c,
        CONTACT_Z + 8.0 + c,
    )
    return plate - cut - pocket


def micro_location() -> Location:
    """The microswitch: hinge up, its lever's tip on the contact line, its
    actuation toward +x."""
    body_top = CONTACT_X - MICRO_LEVER_FREE
    tip_local = MICRO_HINGE_X + MICRO_LEVER_LEN
    centre_z = CONTACT_Z + tip_local
    return Location(
        Plane(
            origin=(body_top - MICRO[2], 0, centre_z), x_dir=(0, 0, -1), z_dir=(1, 0, 0)
        )
    )


def micro_carrier(fit: Fit) -> Part:
    """The plate with a window the switch passes through, and a cheek whose
    pegs go through the switch's holes."""
    c = fit.clearance
    loc = micro_location()
    origin = loc.position
    length, thick, _ = MICRO
    half_t = thick / 2
    plate = _plate_outline(fit) + _spring_seat(CARRIER_UP)
    window = box(
        L.PLATE_X[0] - 1,
        L.PLATE_X[1] + 1,
        -half_t - c,
        half_t + c,
        origin.Z - length / 2 - c,
        origin.Z + length / 2 + c,
    )
    cheek = box(
        L.PLATE_X[0],
        origin.X + MICRO[2] - 1.0,
        -half_t - c - 2.0,
        -half_t - c,
        origin.Z - length / 2 - 1.5,
        origin.Z + length / 2 + 1.5,
    )
    # Pegs stick out sideways in print, so their undersides come to a
    # 45-degree point (toward -x); the point still clears the round hole.
    r = MICRO_HOLE_D / 2 - c - 0.2
    pegs = union(
        teardrop(
            (origin.X + MICRO_HOLE_Z, -half_t - c - 0.01, origin.Z - hx),
            Y,
            r,
            thick + c,
            (-1, 0, 0),
        )
        for hx in (-MICRO_HOLE_PITCH / 2, MICRO_HOLE_PITCH / 2)
    )
    return plate - window + cheek + pegs


def add_switch(m: Module, fit: Fit, trigger: str, presser: str) -> None:
    """The switch plate, its switch, the return spring and the trigger plug
    that every mechanism shares; `presser` is the part that meets the
    switch and the spring."""
    plate = f"switch-plate-{trigger}"
    if trigger == "mx":
        m.add(
            Printed(
                plate,
                mx_plate(fit),
                PLATE_UP,
                MODULE,
                material=PETG,
                perimeters=4,
                infill=60,
            )
        )
        m.add(
            bought(
                "mx-switch",
                Location((MX_FACE_X, 0, CONTACT_Z)),
                "trigger switch",
                MODULE,
            )
        )
    else:
        m.add(
            Printed(
                plate,
                micro_carrier(fit),
                CARRIER_UP,
                MODULE,
                material=PETG,
                perimeters=4,
                infill=60,
            )
        )
        m.add(bought("microswitch", micro_location(), "trigger switch", MODULE))
    # The presser rests on the switch; the switch sits in its plate.
    m.fit(presser, "trigger switch")
    m.fit(plate, "trigger switch")
    m.add(
        bought(
            "spring", Location((L.SPRING_SEAT_X, 0, SPRING_Z)), "return spring", MODULE
        )
    )
    m.fit(plate, "return spring")
    m.fit(presser, "return spring")
    m.add(
        bought(
            "jst-xh2",
            Location((JST_AT[0], JST_AT[1], L.FLOOR_Z - L.CASSETTE_TOP_T - 0.5)),
            "trigger plug",
            MODULE,
        )
    )
    m.add(
        bought(
            "m3x12",
            CASSETTE_SCREW.screw_location(),
            "cassette screw",
            MODULE,
            teardown=True,
        )
    )


# -- the modules ----------------------------------------------------------------------


def _lever_module(fit: Fit, mechanism: str, trigger: str) -> Module:
    body_name, lever_name = MECHANISM_PARTS[mechanism]
    m = Module(MODULE)
    m.add(
        Printed(
            body_name,
            _lever_body(fit, mechanism),
            CASSETTE_UP,
            MODULE,
            material=PETG,
            perimeters=4,
            infill=40,
        )
    )
    m.add(
        Printed(
            lever_name,
            lever_shape(0.0, mechanism),
            LEVER_UP,
            MODULE,
            material=PETG,
            perimeters=4,
            infill=60,
        )
    )
    add_switch(m, fit, trigger, lever_name)
    if mechanism == "filament":
        m.add(bought("pivot-pin", Location((P.X, -11.0, P.Z)), "pivot pin", MODULE))
    else:
        bolt = Location(Plane(origin=(P.X, BOLT_HEAD_Y, P.Z), z_dir=Y))
        m.add(bought("m3x12", bolt, "pivot bolt", MODULE))
        nut = hex_location((P.X, -BOLT_HEAD_Y - M3_NUT_H / 2, P.Z), Y, CASSETTE_UP)
        m.add(bought("m3-nut", nut, "nut, pivot bolt", MODULE))
        m.fit(body_name, "nut, pivot bolt")
    tip = stop_tip_x(trigger)
    m.add(
        bought(
            "m3x12",
            Location(Plane(origin=(tip + 12.0, 0, STOP_Z), z_dir=X)),
            "stop screw",
            MODULE,
        )
    )
    m.add(
        bought(
            "m3-nyloc",
            hex_location((_stop_nut_x(), 0, STOP_Z), X, Y),
            "lock nut, stop screw",
            MODULE,
        )
    )
    m.fit("stop screw", "lock nut, stop screw")  # its nylon ring grips the thread
    return m


@cache
def trigger_module(fit: Fit, mechanism: str, trigger: str) -> Module:
    """The trigger cassette of `mechanism` with the `trigger` switch plate."""
    if mechanism == "button":
        from boresight_case.parts.button import button_module

        return button_module(fit, trigger)
    return _lever_module(fit, mechanism, trigger)
