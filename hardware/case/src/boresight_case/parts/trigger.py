"""The trigger: a module in a pocket at the top of the grip's front, in two
mechanisms on one mount (the pocket, one bolt up into the receiver's
floor, the trigger lead to the hub), both taking the same switch plates.

    receiver's underside
    | top plate                                 front block
    |  tail -> pad -> switch (on a swappable plate)  |
    |   |  arm ---------------------------------> stop screw, up from below
    |   o  pivot, an M3 bolt                        |  mounting bolt, up
    | spring -> blade  <- finger
    |   wall   |

The lever turns between two bosses on its pivot bolt. Pulling the blade
back toward the palm swings its tail, above the pivot, forward onto the
switch: an MX-style switch's stem, or a lever microswitch's tip. An arm
from the tail reaches forward beside the switch; as the tail swings, the
arm's tip drops onto the stop screw, whose height sets where the pull
ends, past the switch's actuation and short of its end of travel. A
ballpoint-pen spring between the blade's back and a wall behind it
returns the lever. The push button (`parts.button`) uses the same housing
outline, bolt and plates.

The housing prints upside down on its top plate; the lever and the
plates print flat.
"""

from __future__ import annotations

import math
from functools import cache

from build123d import Axis, Location, Part, Plane

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
from boresight_case.joints import TRIGGER_BOLT
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
    SPRING,
)

HOUSING_UP = (0, 0, -1)  # printed upside down, on its top plate
LEVER_UP = Y  # printed flat on its -y face
PLATE_UP = (-1, 0, 0)  # the plates print face up
MODULE = "trigger"

P = L.PIVOT
PAD = 2.5  # the pad's face in front of the tail's axis
BACK = 2.0  # the tail's front face elsewhere, recessed so only the pad touches
CONTACT_X = P.X + PAD  # every mechanism meets the switch on this line, at rest
CONTACT_Z = P.Z + L.CONTACT_R
HUB_R = 4.0
BOSS_GAP = 0.25  # each side of the lever, between it and the bosses
W = L.TRIGGER_HALF_W
T = L.TRIGGER_WALL
INNER = W - T  # the housing's inside, each side of the midplane
TOP = L.FLOOR_Z - L.TRIGGER_TOP_T  # the top plate's underside
# The switch plate: 3 mm, sliding down grooves in the side walls through a
# slot in the top plate, resting on the grooves' closed ends.
PLATE_HALF_Y = INNER + 1.0
MX_FACE_X = CONTACT_X + MX_STEM_TOP  # the MX's plate-top face: its stem on the line
PLATE_X = (MX_FACE_X - 1.5, MX_FACE_X + 1.5)  # the MX web is its front 1.5 mm
PLATE_Z = (CONTACT_Z - MX_CUTOUT / 2 - 1.5, L.FLOOR_Z)
BLADE_BOTTOM = -26.0  # below the pivot
SPRING_Z = P.Z - L.SPRING_R
LEAD_HOLE = (-60.0, 6.0)  # x, y of the lead's way up into the grip's bore

# The pivot bolt: an M3 x 12 through the hub, its head and nut sunk into
# the bosses so a 12 mm bolt spans the housing.
BOLT_BOSS_R = 4.5
BOLT_SEAT = 1.2  # boss left under the head, and under the nut
BOLT_HEAD_Y = L.LEVER_W / 2 + BOSS_GAP + BOLT_SEAT  # the head's underside


# -- the lever's motion -----------------------------------------------------------


def pad_travel(angle: float) -> float:
    """How far the pad's face has moved forward along the contact line, at
    `angle` radians of pull."""
    return PAD / math.cos(angle) - PAD + L.CONTACT_R * math.tan(angle)


def angle_for_travel(travel: float) -> float:
    lo, hi = 0.0, math.radians(30)
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if pad_travel(mid) < travel else (lo, mid)
    return (lo + hi) / 2


def arm_drop(angle: float) -> float:
    """How far the arm's underside has dropped at the stop screw's axis, at
    `angle` radians of pull."""
    dx, dz = L.STOP_X - P.X, L.ARM_Z[0]
    t = (dx - dz * math.sin(angle)) / math.cos(angle)
    return dz - (-t * math.sin(angle) + dz * math.cos(angle))


def stop_tip_z(trigger: str) -> float:
    """Where the stop screw's tip sits so the arm meets it at the plate's
    default stop."""
    a = angle_for_travel(L.STOP_TRAVEL[trigger])
    return P.Z + L.ARM_Z[0] - arm_drop(a)


def switch_limits(trigger: str) -> tuple[float, float]:
    """(actuation, end of travel) at the contact, in mm."""
    if trigger == "mx":
        return MX_ACTUATION, MX_TRAVEL
    return MICRO_PRETRAVEL, MICRO_PRETRAVEL + MICRO_OVERTRAVEL


# -- the lever ----------------------------------------------------------------------


def _blade_profile() -> list[tuple[float, float]]:
    """The tail and the blade, about the pivot (dx, dz); the finger's face
    curves forward and back like a trigger shoe."""
    rc = L.CONTACT_R
    pts = [
        (-PAD, rc + 3.0),
        (PAD, rc + 3.0),
        (PAD, rc - 3.0),
        (BACK, rc - 3.0),
        (BACK, -8.0),
        (3.5, -14.0),
        (4.0, -20.0),
        (2.5, BLADE_BOTTOM),
        (-1.5, BLADE_BOTTOM),
        (-PAD, BLADE_BOTTOM + 4.0),
    ]
    return [(P.X + dx, P.Z + dz) for dx, dz in pts]


def lever_shape(angle: float = 0.0) -> Part:
    """The lever, turned `angle` radians toward the pull."""
    half = L.LEVER_W / 2
    body = side_profile(_blade_profile(), -half, half)
    body = body + cylinder((P.X, -half, P.Z), Y, HUB_R, L.LEVER_W)
    # The arm: from the blade forward, under the switch, to the stop screw.
    a0, a1 = L.ARM_Z
    arm = box(P.X, L.STOP_X + 2.5, -half, half, P.Z + a0, P.Z + a1)
    body = body + arm
    body = body - cylinder((P.X, -half - 1, P.Z), Y, M3_CLEAR / 2, L.LEVER_W + 2)
    if angle:
        body = body.rotate(Axis((P.X, 0, P.Z), (0, 1, 0)), math.degrees(angle))
    return body


def lever_sweep(trigger: str, steps: int = 6) -> Part:
    """Every position of the lever from rest to the stop."""
    end = angle_for_travel(L.STOP_TRAVEL[trigger])
    return union(lever_shape(end * k / steps) for k in range(steps + 1))


# -- the housing every mechanism shares ------------------------------------------------


# Behind this, the rear part's top slopes down at 45 degrees, under the
# front of the grip's tenon, so the grip keeps material under its tenon and
# both print without support.
SLOPE_X = -55.75


def outline() -> list[tuple[float, float]]:
    """The housing's side view (x, z): the rear part in the grip's pocket,
    the wall behind the blade, round the pivot, under the switch and the
    front block."""
    x0, x1 = L.TRIGGER_X
    w0, w1 = L.SPRING_WALL_X
    f0 = L.FRONT_BLOCK_X[0]
    return [
        (SLOPE_X, L.FLOOR_Z),
        (x1, L.FLOOR_Z),
        (x1, L.FRONT_BLOCK_BOTTOM),
        (f0, L.FRONT_BLOCK_BOTTOM),
        (f0, PLATE_Z[0] - 1.5),
        (P.X + 6.0, PLATE_Z[0] - 1.5),
        (P.X + 6.0, P.Z - 7.0),
        (w1, P.Z - 7.0),
        (w1, L.TRIGGER_Z[0]),
        (w0, L.TRIGGER_Z[0]),
        (w0, -46.0),
        (x0, -46.0),
        (x0, L.FLOOR_Z - (SLOPE_X - x0)),
    ]


def pocket_outline(clearance: float) -> Part:
    """What the grip gives up for the housing: its outline, grown by the
    clearance, through the housing's width."""
    pts = outline()
    xs = [x for x, _ in pts]
    out = side_profile(pts, -W - clearance, W + clearance)
    # Grow it backward and down by the clearance (the rear and the wall are
    # where the housing meets the grip).
    from build123d import Location as Loc

    return out + Loc((-clearance, 0, 0)) * out + Loc((0, 0, -clearance)) * out & box(
        min(xs) - 5, max(xs), -30, 30, -100, L.FLOOR_Z
    )


def _hollow() -> Part:
    """The inside: between the side walls, under the top plate, where the
    lever, the switch and the plate move."""
    w1 = L.SPRING_WALL_X[1]
    f0 = L.FRONT_BLOCK_X[0]
    return side_profile(
        [
            (w1, TOP),
            (f0, TOP),
            (f0, PLATE_Z[0] - 2.5),
            (P.X + 6.0 - 0.01, PLATE_Z[0] - 2.5),
            (P.X + 6.0 - 0.01, P.Z - 7.01),
            (w1, P.Z - 7.01),
        ],
        -INNER,
        INNER,
    ) + box(w1, P.X + 6.0, -INNER, INNER, L.TRIGGER_Z[0] - 1, P.Z - 7.0)


def shared_body(fit: Fit, plate_dx: float = 0.0) -> Part:
    """Top plate, side walls, the rear part, the spring wall and the front
    block, with the switch plate's grooves and slot (moved back `plate_dx`
    for the button), the lead's way out and the mounting bolt's hole: what
    every mechanism keeps."""
    c = fit.clearance
    body = side_profile(outline(), -W, W) - _hollow()
    cuts = [
        # The switch plate's grooves (closed at their bottom, where the
        # plate rests) and its slot through the top plate.
        box(
            PLATE_X[0] + plate_dx - c,
            PLATE_X[1] + plate_dx + c,
            -PLATE_HALF_Y - c,
            PLATE_HALF_Y + c,
            PLATE_Z[0],
            L.FLOOR_Z + 0.5,
        ),
        lead_way(),
        bolt_way(),
    ]
    return body - union(cuts)


def lead_way() -> Part:
    """The trigger lead: from inside, back through the spring wall and up
    through the top plate into the grip's bore."""
    x, y = LEAD_HOLE
    w0, w1 = L.SPRING_WALL_X
    up = cylinder((x, y, TOP - 4.0), Z, 2.5, L.TRIGGER_TOP_T + 5.0)
    back = box(x - 2.5, w1 + 0.5, y - 2.5, y + 2.5, TOP - 6.5, TOP - 1.5)
    return up + back


def bolt_way() -> Part:
    """The mounting bolt's hole through the top plate, and the way up the
    right side wall's inside for its head and the hex key from below."""
    e = TRIGGER_BOLT.entry
    hole = cylinder((e[0], e[1], e[2] - 0.5), Z, M3_CLEAR / 2, L.FLOOR_Z - e[2] + 1)
    way = cylinder((e[0], e[1], e[2] + 0.01), (0, 0, -1), M3_HEAD_CBORE / 2, 60.0)
    return hole + way


def key_way() -> Part:
    """The hex key's way up to the mounting bolt's head, from below."""
    e = TRIGGER_BOLT.entry
    return cylinder((e[0], e[1], e[2] - 0.01), (0, 0, -1), 1.6, 60.0)


def _lever_body(fit: Fit) -> Part:
    body = shared_body(fit) + bolt_bosses(P.X, P.Z) + _spring_seat()
    cuts = [*_bolt_cuts(fit), _stop_cuts(fit), _arm_slot(fit), bolt_way()]
    return body - union(cuts)


SEAT_T = 1.0  # the spring seat's boss on the wall


def _spring_seat() -> Part:
    """A boss on the spring wall's face, and a spigot into the spring."""
    face = L.SPRING_WALL_X[1]
    # Sideways in print, so their undersides come to a 45-degree point.
    boss = teardrop((face - 0.01, 0, SPRING_Z), X, 3.25, SEAT_T + 0.01, Z)
    spigot = teardrop((face + SEAT_T, 0, SPRING_Z), X, 1.75, 3.0, Z)
    return boss + spigot


def bolt_bosses(x: float, z: float) -> Part:
    """Bosses on both side walls' insides round a bolt across the housing."""
    inner = L.LEVER_W / 2 + BOSS_GAP
    return union(
        teardrop(
            (x, sign * (INNER + 0.01), z),
            (0, -sign, 0),
            BOLT_BOSS_R,
            INNER - inner,
            Z,
        )
        for sign in (1, -1)
    )


def _bolt_cuts(fit: Fit, x: float = P.X, z: float = P.Z) -> list[Part]:
    """A bolt's bore through both bosses and walls, its head's counterbore
    from the left, its nut's pocket from the right."""
    bore = teardrop((x, -W - 0.5, z), Y, M3_CLEAR / 2, 2 * W + 1, HOUSING_UP)
    head = teardrop(
        (x, BOLT_HEAD_Y, z), Y, M3_HEAD_CBORE / 2, W - BOLT_HEAD_Y + 0.5, HOUSING_UP
    )
    nut_len = W - BOLT_HEAD_Y + 0.5
    nut = hexagon_prism(
        (x, -BOLT_HEAD_Y - nut_len / 2, z), Y, fit.nut_af, nut_len, HOUSING_UP
    )
    return [bore, head, nut]


def bolt_across(m: Module, x: float, z: float, label: str, part: str) -> None:
    """An M3 x 12 across the housing at (x, z), its nut pressed in."""
    bolt = Location(Plane(origin=(x, BOLT_HEAD_Y, z), z_dir=Y))
    m.add(bought("m3x12", bolt, label, MODULE))
    nut = hex_location((x, -BOLT_HEAD_Y - M3_NUT_H / 2, z), Y, HOUSING_UP)
    m.add(bought("m3-nut", nut, f"nut, {label}", MODULE))
    m.fit(part, f"nut, {label}")


def stop_nut_z() -> float:
    return L.FRONT_BLOCK_BOTTOM + 8.0


def _stop_cuts(fit: Fit) -> Part:
    """The stop screw's hole up through the front block, and a slot from
    the block's front face that its lock nut drops into."""
    c = fit.clearance
    hole = cylinder((L.STOP_X, L.STOP_Y, L.FRONT_BLOCK_BOTTOM - 1), Z, M3_CLEAR / 2, 20)
    # The head sinks up into the block as the stop is raised.
    head = cylinder(
        (L.STOP_X, L.STOP_Y, L.FRONT_BLOCK_BOTTOM - 1), Z, M3_HEAD_CBORE / 2, 4.5
    )
    hole = hole + head
    nz = stop_nut_z()
    r = M3_NUT_AF / math.sqrt(3)
    slot = box(
        L.STOP_X - r - c,
        L.TRIGGER_X[1] + 0.5,
        L.STOP_Y - M3_NUT_AF / 2 - c,
        L.STOP_Y + M3_NUT_AF / 2 + c,
        nz - M3_NYLOC_H / 2 - c,
        nz + M3_NYLOC_H / 2 + c,
    )
    return hole + slot


def _arm_slot(fit: Fit) -> Part:
    """Room in the front block for the arm's tip to drop to the stop."""
    c = fit.clearance
    half = L.LEVER_W / 2
    return box(
        L.FRONT_BLOCK_X[0] - 0.01,
        L.STOP_X + 2.5 + 1.0,
        -half - 0.5,
        half + 0.5,
        P.Z + L.ARM_Z[0] - 6.0,
        P.Z + L.ARM_Z[1] + c + 0.5,
    )


# -- switch plates --------------------------------------------------------------------


def _plate_outline(fit: Fit) -> Part:
    c = fit.clearance
    return box(
        PLATE_X[0],
        PLATE_X[1],
        -PLATE_HALF_Y + c,
        PLATE_HALF_Y - c,
        PLATE_Z[0] + c,
        PLATE_Z[1] - c,
    )


# The trigger lead's way past the plate, at its top corner on the left.
LEAD_Y = INNER - 1.35
LEAD_R = 1.0


def _lead_notch() -> Part:
    return box(
        PLATE_X[0] - 1,
        PLATE_X[1] + 1,
        LEAD_Y - LEAD_R - 0.3,
        PLATE_HALF_Y + 1,
        TOP - 4.5,
        PLATE_Z[1] + 1,
    )


def mx_plate(fit: Fit) -> Part:
    """A 3 mm plate: the 14 mm cut-out through its 1.5 mm front web, and a
    counterbore behind it for the switch's housing to sit in."""
    c = fit.clearance
    plate = _plate_outline(fit)
    cut = box(
        PLATE_X[0] - 1,
        PLATE_X[1] + 1,
        -MX_CUTOUT / 2,
        MX_CUTOUT / 2,
        CONTACT_Z - MX_CUTOUT / 2,
        CONTACT_Z + MX_CUTOUT / 2,
    )
    pocket = box(
        PLATE_X[0] - 1,
        MX_FACE_X,
        -8.0 - c,
        8.0 + c,
        CONTACT_Z - 8.0 - c,
        CONTACT_Z + 8.0 + c,
    )
    return plate - cut - pocket - _lead_notch()


def mx_location(contact_x: float = CONTACT_X, facing: int = -1) -> Location:
    """The MX switch with its stem on the contact line, pointing along
    `facing` (-1: back toward the lever's tail)."""
    face = contact_x - facing * MX_STEM_TOP
    return Location(
        Plane(origin=(face, 0, CONTACT_Z), x_dir=(facing, 0, 0), z_dir=(0, 0, 1))
    )


def micro_location(contact_x: float = CONTACT_X, facing: int = -1) -> Location:
    """The microswitch: hinge down, its lever's tip on the contact line,
    its lever facing along `facing`."""
    pins = contact_x - facing * (MICRO_LEVER_FREE + MICRO[2])
    tip_local = MICRO_HINGE_X + MICRO_LEVER_LEN
    return Location(
        Plane(
            origin=(pins, 0, CONTACT_Z - tip_local),
            x_dir=(0, 0, 1),
            z_dir=(facing, 0, 0),
        )
    )


def micro_carrier(fit: Fit) -> Part:
    """The plate with a window the switch passes through, and a cheek whose
    pegs go through the switch's holes."""
    c = fit.clearance
    origin = micro_location().position
    length, thick, height = MICRO
    half_t = thick / 2
    plate = _plate_outline(fit)
    lo = origin.Z - length / 2  # the body's lower end
    window = box(
        PLATE_X[0] - 1,
        PLATE_X[1] + 1,
        -half_t - c,
        half_t + c,
        PLATE_Z[0] - 1,
        min(lo + length + c, PLATE_Z[1] - 2.0),
    )
    # The cheek reaches back from the plate along the switch's -y side, to
    # just short of the lever's hinge end.
    body_front = origin.X - height
    cheek = box(
        body_front + 1.0,
        PLATE_X[1],
        -half_t - c - 2.0,
        -half_t - c,
        origin.Z - MICRO_HOLE_PITCH / 2 - 2.5,
        TOP - c,
    )
    r = MICRO_HOLE_D / 2 - c - 0.2
    pegs = union(
        teardrop(
            (
                origin.X - MICRO_HOLE_Z,
                -half_t - c - 0.01,
                origin.Z + MICRO_HOLE_PITCH / 2 + k,
            ),
            Y,
            r,
            thick + c,
            X,  # sideways in print: their undersides come to a point
        )
        for k in (-MICRO_HOLE_PITCH, 0.0)
    )
    return plate - window + cheek + pegs - _lead_notch()


def add_switch(
    m: Module,
    fit: Fit,
    trigger: str,
    presser: str,
    facing: int = -1,
    contact_x: float = CONTACT_X,
    plate_dx: float = 0.0,
) -> None:
    """The switch plate and its switch, which every mechanism shares;
    `presser` is the part that meets the switch. The button mounts the same
    plate turned round (`facing` +1) and moved back by `plate_dx`."""
    plate = f"switch-plate-{trigger}"
    shape = mx_plate(fit) if trigger == "mx" else micro_carrier(fit)
    where = Location()
    if facing > 0:
        mid = (PLATE_X[0] + PLATE_X[1]) / 2
        where = (
            Location((plate_dx, 0, 0))
            * Location(Plane(origin=(mid, 0, 0), x_dir=(-1, 0, 0), z_dir=(0, 0, 1)))
            * Location((-mid, 0, 0))
        )
    m.add(
        Printed(
            plate,
            where * shape,
            PLATE_UP if facing < 0 else X,
            MODULE,
            material=PETG,
            perimeters=4,
            infill=60,
        )
    )
    loc = (mx_location if trigger == "mx" else micro_location)(contact_x, facing)
    key = "mx-switch" if trigger == "mx" else "microswitch"
    m.add(bought(key, loc, "trigger switch", MODULE))
    m.fit(presser, "trigger switch")  # the presser rests on the switch
    m.fit(plate, "trigger switch")


def add_mount(m: Module, fit: Fit) -> None:
    """The mounting bolt and its nut in the receiver's floor."""
    m.add(
        bought(
            "m3x12",
            TRIGGER_BOLT.screw_location(),
            "trigger bolt",
            MODULE,
            teardown=True,
        )
    )
    if fit.fastener == "insert":
        m.add(
            bought(
                "m3-insert",
                TRIGGER_BOLT.insert_location(),
                "insert, trigger bolt",
                MODULE,
            )
        )
    else:
        from boresight_case.parts.receiver import UP as RECEIVER_UP

        m.add(
            bought(
                "m3-nut",
                TRIGGER_BOLT.nut_location(fit, RECEIVER_UP),
                "nut, trigger bolt",
                MODULE,
            )
        )
    m.fit("receiver", m.bought[-1].label)


# -- the modules ----------------------------------------------------------------------


def _lever_module(fit: Fit, trigger: str) -> Module:
    body_name, lever_name = MECHANISM_PARTS["bolt"]
    m = Module(MODULE)
    m.add(
        Printed(
            body_name,
            _lever_body(fit),
            HOUSING_UP,
            MODULE,
            material=PETG,
            perimeters=4,
            infill=40,
        )
    )
    m.add(
        Printed(
            lever_name,
            lever_shape(0.0),
            LEVER_UP,
            MODULE,
            material=PETG,
            perimeters=4,
            infill=60,
        )
    )
    add_switch(m, fit, trigger, lever_name)
    add_mount(m, fit)
    bolt_across(m, P.X, P.Z, "pivot bolt", body_name)
    tip = stop_tip_z(trigger)
    m.add(
        bought(
            "m3x12",
            Location(Plane(origin=(L.STOP_X, L.STOP_Y, tip - 12.0), z_dir=(0, 0, -1))),
            "stop screw",
            MODULE,
        )
    )
    m.add(
        bought(
            "m3-nyloc",
            hex_location((L.STOP_X, L.STOP_Y, stop_nut_z()), Z, X),
            "lock nut, stop screw",
            MODULE,
        )
    )
    m.fit("stop screw", "lock nut, stop screw")  # its nylon ring grips the thread
    m.add(
        bought(
            "spring",
            Location((L.SPRING_WALL_X[1] + SEAT_T, 0, SPRING_Z)),
            "return spring",
            MODULE,
        )
    )
    m.fit(body_name, "return spring")  # on its spigot
    m.fit(lever_name, "return spring")
    return m


@cache
def trigger_module(fit: Fit, mechanism: str, trigger: str) -> Module:
    """The trigger module of `mechanism` with the `trigger` switch plate."""
    if mechanism == "button":
        from boresight_case.parts.button import button_module

        return button_module(fit, trigger)
    return _lever_module(fit, trigger)


def trigger_lead_path(mechanism: str = "bolt") -> list[tuple[float, float, float]]:
    """The lead from the switch's pins up into the grip's bore, where the
    hub's trigger socket takes it from below. For the blade it runs back
    along the housing's left wall under the top plate, past the plate's
    notch and through the spring wall; for the button the switch is at the
    back already."""
    x, y = LEAD_HOLE
    under = TOP - 3.0
    if mechanism == "button":
        return [(x - 1.0, y, CONTACT_Z), (x, y, under), (x, y, TOP)]
    return [
        (CONTACT_X + 18.0, LEAD_Y, CONTACT_Z),
        (CONTACT_X + 18.0, LEAD_Y, under),
        (L.SPRING_WALL_X[1] + 2.5, y + 1.5, under),
        (L.SPRING_WALL_X[0] - 1.0, y, under),
        (x, y, TOP),
    ]


__all__ = ["trigger_module", "lever_sweep", "SPRING"]
