"""The carriers: modules on a plate that slides along a bone's rails.

Each is a 2 mm plate whose top and bottom edges ride the C-channels on one
inner wall, held lengthwise by the next one in its run, by printed spacers
and, at the run's ends, by whatever fills the bone's ports. No screw,
glue, snap or latch holds a carrier: it comes out once the bone in front
of it (or the rear cap) is off. A board on a carrier is held by M2.5
screws into nuts in printed bosses; none of them is undone in a teardown.

- the hub, on the receiver's left rails above the grip: the regulator,
  the ideal diode, the power switch, the LEDs, a socket for every lead and
  the 5 V and GND test pins;
- the Start and Select buttons, on the left rails ahead of it;
- a feedback device, on the right rails: a vibration motor, a solenoid or
  an LRA, each with its driver;
- the Pi's retainer, on the barrel's right rails, whose posts hold the Pi
  on its sled's pegs;
- spacers, which fill the rest of a run.

Every plate prints flat on its outer face.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache

from build123d import Location, Part, Plane

from boresight_case import layout as L
from boresight_case.geom import (
    Z,
    box,
    cylinder,
    hex_location,
    hexagon_prism,
    teardrop,
    union,
)
from boresight_case.interfaces import Fit, carrier_plate
from boresight_case.model import Bought, Module, Printed, bought
from boresight_case.vendor import (
    JST_BEND,
    JST_BEND_TIGHT,
    JST_XH,
    JST_XH_PITCH,
    M2_5,
    PERFBOARD,
    PERFBOARD_T,
    SLIDE_LEVER,
    SLIDE_THROW,
    SOLENOID,
    SOLENOID_REACH,
)


def up(side: int) -> tuple[float, float, float]:
    """A plate on the `side` wall prints with its inner face up."""
    return (0.0, -float(side), 0.0)


def face_y(side: int) -> float:
    """The plate's inner face."""
    return L.plate_y(side)[0]


def on_face(side: int, x: float, z: float, off: float = 0.0) -> Location:
    """A frame on the plate's inner face at (x, z), `off` in from it, its z
    pointing into the bone."""
    y = face_y(side) - side * off
    return Location(Plane(origin=(x, y, z), x_dir=(1, 0, 0), z_dir=(0, -side, 0)))


def toward_wall(side: int, x: float, y: float, z: float) -> Location:
    """A frame at (x, y, z) with its z pointing out through the wall."""
    return Location(Plane(origin=(x, y, z), x_dir=(1, 0, 0), z_dir=(0, side, 0)))


def boss(side: int, x: float, z: float, height: float, r: float = 2.75) -> Part:
    """A round boss on the plate's inner face."""
    return cylinder((x, face_y(side) + side * 0.01, z), (0, -side, 0), r, height + 0.01)


def screw_boss(
    side: int, x: float, z: float, height: float, fit: Fit, r: float = 3.0
) -> tuple[Part, Part]:
    """(a boss with an M2.5 nut in it, its cuts): the screw comes in from the
    board on top of the boss, the nut drops into a slot from the boss's
    side, 2.5 mm below its top."""
    hole_d, _, _, af, nut_h = M2_5
    c = fit.clearance
    b = boss(side, x, z, height, r)
    top = face_y(side) - side * height
    hole = cylinder(
        (x, top - side * 0.5, z), (0, side, 0), hole_d / 2, height + L.PLATE_T + 1
    )
    nut_y = top + side * (1.0 + nut_h / 2)
    slot = box(
        x - af / 2 - c,
        x + af / 2 + c,
        nut_y - nut_h / 2 - c,
        nut_y + nut_h / 2 + c,
        z - r - 1,
        z + af / 2 + c,
    )
    return b, hole + slot


def board_screw(
    side: int,
    x: float,
    z: float,
    height: float,
    board_t: float,
    label: str,
    module: str,
) -> list[Bought]:
    """The M2.5 screw through a board resting on a boss `height` tall, and
    its nut in the boss."""
    _, _, _, _, nut_h = M2_5
    top = face_y(side) - side * height
    head = top - side * board_t
    screw = Location(Plane(origin=(x, head, z), z_dir=(0, -side, 0)))
    nut_y = top + side * (1.0 + nut_h / 2)
    nut = Location(Plane(origin=(x, nut_y, z), z_dir=(0, 1, 0)))
    return [
        bought("m2.5x6", screw, label, module),
        bought("m2.5-nut", nut, f"nut, {label}", module),
    ]


def _plate(name: str, x0: float, x1: float, side: int, module: str) -> Printed:
    return Printed(
        name, carrier_plate(x0, x1, side), up(side), module, perimeters=3, infill=30
    )


# -- spacers ---------------------------------------------------------------------


def spacer(length: float, side: int, x0: float, fit: Fit, index: int = 0) -> Printed:
    """A plain plate filling `length` of a run from x0, a clearance short so
    the run's stack slides home. One file per length, whichever wall."""
    x1 = x0 + length - fit.clearance
    shape = carrier_plate(x0, x1, side)
    name = f"spacer-{length:g}"
    inst = f"{name} {'left' if side > 0 else 'right'}{f' {index}' if index else ''}"
    return Printed(inst, shape, up(side), "spacer", perimeters=2, infill=20, part=name)


# -- the hub ---------------------------------------------------------------------

HUB_SIDE = +1
STANDOFF = 7.0  # the plate's face to the perfboard's back
BOARD_BACK = face_y(HUB_SIDE) - STANDOFF  # 6.25
BOARD_FRONT = BOARD_BACK - PERFBOARD_T
BOARD_X = (L.HUB_X[0] + 1.0, L.HUB_X[0] + 1.0 + PERFBOARD[0])  # -87 .. -47
BOARD_Z = (-12.0, -12.0 + PERFBOARD[1])  # -12 .. 20
HUB_BOSSES = ((-84.5, -9.5), (-84.5, 15.0), (-70.0, -9.5), (-70.0, 15.0))
HUB_SCREWS = (HUB_BOSSES[1], HUB_BOSSES[2])


def jst_width(ways: int) -> float:
    return ways * JST_XH_PITCH + 3.4


@dataclass(frozen=True)
class Socket:
    """A JST-XH socket on the hub: its lead, its ways and where it sits."""

    lead: str
    ways: int
    x: float  # its centre
    z: float
    down: bool = False  # mating downward from the perfboard's bottom edge


# The hub's sockets, one per lead. Front face: mating toward the middle of
# the receiver. The battery and the trigger take theirs from below, out of
# the grip's bore.
# The battery's and the trigger's take their plugs from below, out of the
# grip's bore: ways across y, between the grip bolt's crush bar and the
# grip socket's front rib.
SOCKETS = (
    Socket("battery", 2, -76.25 + JST_XH[0] / 2, L.FLOOR_Z, down=True),
    Socket("trigger", 2, -64.25 - JST_XH[0] / 2, L.FLOOR_Z, down=True),
    Socket("feedback", 4, -87.0 + jst_width(4) / 2, -8.1),
    Socket("esp32-cam", 6, -66.0 + jst_width(6) / 2, -8.1),
    Socket("pi power", 2, -75.0 + jst_width(2) / 2, -1.6),
    Socket("buttons", 3, -64.0 + jst_width(3) / 2, -1.6),
    Socket("pi signal", 10, -76.0 + jst_width(10) / 2, 4.9),
)
TEST_PINS = (-50.0, -1.6)
FUSE_AT = (-58.0, 15.0)
DIODE_AT = (-74.0, 13.5)


def socket(name: str) -> Socket:
    return next(s for s in SOCKETS if s.lead == name)


def _down_y(s: Socket) -> float:
    return BOARD_FRONT - jst_width(s.ways) / 2


def socket_location(s: Socket) -> Location:
    if s.down:
        return Location(
            Plane(
                origin=(s.x, _down_y(s), BOARD_Z[0]), x_dir=(0, 1, 0), z_dir=(0, 0, -1)
            )
        )
    return Location(
        Plane(origin=(s.x, BOARD_FRONT, s.z), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
    )


def socket_key(s: Socket) -> str:
    """The downward sockets' plugs turn their wires at once, to clear the
    grip's crush bar and the trigger housing below them."""
    return "jst-xh2-tight" if s.down else f"jst-xh{s.ways}"


def socket_mouth(s: Socket) -> tuple[float, float, float]:
    """Where a lead leaves its plug, beyond the bend room."""
    if s.down:
        return (s.x, _down_y(s), BOARD_Z[0] - JST_XH[1] - JST_BEND_TIGHT)
    return (s.x, BOARD_FRONT - JST_XH[1] - JST_BEND + 1.5, s.z)


def _hub_plate(fit: Fit) -> Part:
    side = HUB_SIDE
    c = fit.clearance
    plate = carrier_plate(*L.HUB_X, side)
    bosses, cuts = [], []
    for x, z in HUB_BOSSES:
        if (x, z) in HUB_SCREWS:
            b, cut = screw_boss(side, x, z, STANDOFF, fit)
            bosses.append(b)
            cuts.append(cut)
        else:
            bosses.append(boss(side, x, z, STANDOFF, 2.75))
    # The switch's knob, and the LEDs, out through the plate.
    kx, ky, _ = SLIDE_LEVER
    x, z = L.SWITCH_AT
    half = (kx + SLIDE_THROW) / 2 + 0.5 + c
    inner, outer = L.plate_y(side)
    cuts.append(
        box(
            x - half,
            x + half,
            inner - 0.5,
            outer + 0.5,
            z - ky / 2 - c - 0.5,
            z + ky / 2 + c + 0.5,
        )
    )
    for lx, lz in (L.POWER_LED_AT, L.STATUS_LED_AT):
        cuts.append(cylinder((lx, inner - 0.5, lz), (0, 1, 0), 1.75, 3.0))
    return plate + union(bosses) - union(cuts)


def hub_parts() -> list[Bought]:
    """Everything bought on the hub, placed."""
    m = "hub"
    side = HUB_SIDE
    cx = (BOARD_X[0] + BOARD_X[1]) / 2
    cz = (BOARD_Z[0] + BOARD_Z[1]) / 2
    # The perfboard's frame has its back on z=0: z=0 on the board's back.
    out = [
        bought(
            "perfboard",
            Location(
                Plane(origin=(cx, BOARD_BACK, cz), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
            ),
            "hub perfboard",
            m,
        )
    ]
    for i, (x, z) in enumerate(HUB_SCREWS):
        out += board_screw(side, x, z, STANDOFF, PERFBOARD_T, f"hub screw {i + 1}", m)
    # Behind the perfboard: the switch, the LEDs, the regulator.
    sx, sz = L.SWITCH_AT
    out.append(
        bought("slide-switch", toward_wall(side, sx, BOARD_BACK, sz), "power switch", m)
    )
    for (lx, lz), label in (
        (L.POWER_LED_AT, "power LED"),
        (L.STATUS_LED_AT, "status LED"),
    ):
        out.append(
            bought("led3", toward_wall(side, lx, face_y(side) - 1.35, lz), label, m)
        )
    reg = Location(
        Plane(origin=(-57.0, BOARD_BACK + 1.05, 6.0), x_dir=(0, 0, 1), z_dir=(0, 1, 0))
    )
    out.append(bought("buck-boost", reg, "regulator", m))
    # In front of it: the ideal diode, the sockets, the test pins.
    diode = Location(
        Plane(
            origin=(*DIODE_AT[:1], BOARD_FRONT, DIODE_AT[1]),
            x_dir=(1, 0, 0),
            z_dir=(0, -1, 0),
        )
    )
    out.append(bought("ideal-diode", diode, "ideal diode", m))
    for s in SOCKETS:
        out.append(bought(socket_key(s), socket_location(s), f"{s.lead} socket", m))
    tx, tz = TEST_PINS
    out.append(
        bought(
            "test-pins",
            Location(
                Plane(origin=(tx, BOARD_FRONT, tz), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
            ),
            "5 V and GND test pins",
            m,
        )
    )
    out.append(
        bought(
            "polyfuse",
            Location(
                Plane(
                    origin=(*FUSE_AT[:1], BOARD_FRONT, FUSE_AT[1]),
                    x_dir=(1, 0, 0),
                    z_dir=(0, -1, 0),
                )
            ),
            "solenoid fuse",
            m,
        )
    )
    return out


@cache
def hub(fit: Fit) -> Module:
    m = Module("hub")
    m.add(_plate("hub", *L.HUB_X, HUB_SIDE, "hub"))
    m.printed[0].shape = _hub_plate(fit)
    m.add(*hub_parts())
    for label in ("hub screw 1", "hub screw 2"):
        m.fit("hub perfboard", label)
        m.fit("hub", f"nut, {label}")
    m.fit("hub", "hub perfboard")  # it rests on the standoffs, its wiring between
    # Soldered to the perfboard: their pins go through it.
    for b in m.bought:
        if b.label not in ("hub perfboard",) and not b.label.startswith(
            ("hub screw", "nut,")
        ):
            m.fit("hub perfboard", b.label)
    return m


# -- the Start and Select buttons ------------------------------------------------------

BUTTON_SIDE = +1
BUTTON_BACK = face_y(BUTTON_SIDE) - 6.75  # the small perfboard's back
BUTTON_SCREW = (-35.0, 6.5)


@cache
def button_panel(fit: Fit) -> Module:
    side = BUTTON_SIDE
    m = Module("buttons")
    plate = carrier_plate(*L.BUTTONS_X, side)
    b, cut = screw_boss(side, *BUTTON_SCREW, face_y(side) - BUTTON_BACK, fit)
    inner, outer = L.plate_y(side)
    holes = union(
        cylinder((x, inner - 0.5, z), (0, 1, 0), 2.2, 3.0) for x, z in L.BUTTON_AT
    )
    m.add(
        Printed(
            "button-panel",
            plate + b - cut - holes,
            up(side),
            "buttons",
            perimeters=3,
            infill=30,
        )
    )
    cx = (L.BUTTONS_X[0] + L.BUTTONS_X[1]) / 2
    board = Location(
        Plane(origin=(cx, BUTTON_BACK, 1.0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
    )
    m.add(bought("perfboard-small", board, "button perfboard", "buttons"))
    m.add(
        *board_screw(
            side,
            *BUTTON_SCREW,
            face_y(side) - BUTTON_BACK,
            PERFBOARD_T,
            "button screw",
            "buttons",
        )
    )
    m.fit("button perfboard", "button screw")
    m.fit("button-panel", "nut, button screw")
    m.fit("button-panel", "button perfboard")  # on its boss, its wiring behind
    for (x, z), label in zip(
        L.BUTTON_AT, ("Start button", "Select button"), strict=True
    ):
        m.add(bought("tact-13", toward_wall(side, x, BUTTON_BACK, z), label, "buttons"))
        m.fit("button perfboard", label)
    return m


# -- the feedback carriers -------------------------------------------------------------

FB_SIDE = -1
FB_X = L.FEEDBACK_X
FB_LEAD_AT = (FB_X[0] + 4.0, 12.0)  # where each carrier's lead leaves it


def _ring(
    side: int, x: float, z: float, inner_r: float, height: float, fit: Fit
) -> Part:
    """A ring on the plate that a coin device sits in."""
    outer = cylinder(
        (x, face_y(side) + side * 0.01, z), (0, -side, 0), inner_r + 2.0, height + 0.01
    )
    hole = cylinder(
        (x, face_y(side) + side * 1.0, z),
        (0, -side, 0),
        inner_r + fit.clearance,
        height + 2.0,
    )
    return outer - hole


def _coin_carrier(
    fit: Fit, name: str, device: str, driver: str, driver_size, label: str
) -> Module:
    """A coin device (the vibration motor, the LRA) in a ring, with its
    driver board screwed down over half of it, so the board traps it."""
    side = FB_SIDE
    m = Module("feedback")
    dev_x, dev_z = -40.0, 4.0
    thick = 3.6
    plate = carrier_plate(FB_X[0], FB_X[1] - fit.clearance, side)
    ring = _ring(side, dev_x, dev_z, 5.0, thick, fit)
    length, width, _ = driver_size
    bx = dev_x + 3.0 + length / 2 - 5.0  # the board covers the device's +x half
    sx = bx + length / 2 - 2.5  # the screw, near the board's far end
    b, cut = screw_boss(side, sx, dev_z, thick, fit)
    m.add(
        Printed(
            name, plate + ring + b - cut, up(side), "feedback", perimeters=3, infill=30
        )
    )
    m.add(bought(device, on_face(side, dev_x, dev_z), label, "feedback"))
    m.fit(name, label)  # pressed into its ring
    m.add(
        bought(driver, on_face(side, bx, dev_z, thick), f"{label} driver", "feedback")
    )
    m.add(
        *board_screw(side, sx, dev_z, thick, 1.6, f"{label} driver screw", "feedback")
    )
    m.fit(f"{label} driver", f"{label} driver screw")
    m.fit(name, f"nut, {label} driver screw")
    return m


def _solenoid_carrier(fit: Fit) -> Module:
    """The solenoid on its back, its plunger forward into a printed anvil
    at the plate's front end, held down by a printed strap screwed over
    it; its MOSFET module below."""
    side = FB_SIDE
    m = Module("feedback")
    length, width, height = SOLENOID
    # Clear of the hub's sockets, which reach across behind it.
    sol_x = -44.5  # the frame's back
    sol_z = 5.0
    plate = carrier_plate(FB_X[0], FB_X[1] - fit.clearance, side)
    anvil_x = sol_x + length + SOLENOID_REACH
    anvil = box(
        anvil_x,
        FB_X[1] - fit.clearance,
        face_y(side) - side * 11.0,
        face_y(side) + side * 0.01,
        sol_z - 4.0,
        sol_z + 4.0,
    )
    strap_x = sol_x + length / 2
    feet = ((strap_x, sol_z - width / 2 - 3.0), (strap_x, sol_z + width / 2 + 3.0))
    bosses, cuts = [], []
    for fx, fz in feet:
        b, cut = screw_boss(side, fx, fz, height, fit, r=2.75)
        bosses.append(b)
        cuts.append(cut)
    mos_x, mos_z = -22.0, -7.0
    b, cut = screw_boss(side, mos_x - 3.5, mos_z, 2.0, fit, r=2.5)
    bosses.append(b)
    cuts.append(cut)
    m.add(
        Printed(
            "feedback-solenoid",
            plate + anvil + union(bosses) - union(cuts),
            up(side),
            "feedback",
            perimeters=4,
            infill=40,
        )
    )
    # The strap: a bridge over the frame from foot to foot.
    y_top = face_y(side) - side * height
    strap = box(
        strap_x - 4.0,
        strap_x + 4.0,
        y_top - side * 2.0,
        y_top,
        feet[0][1] - 2.75,
        feet[1][1] + 2.75,
    )
    hole_d = M2_5[0]
    strap = strap - union(
        cylinder((fx, y_top + side * 1.0, fz), (0, -side, 0), hole_d / 2, 4.0)
        for fx, fz in feet
    )
    m.add(
        Printed(
            "solenoid-strap", strap, (0, side, 0), "feedback", perimeters=3, infill=40
        )
    )
    frame = Location(
        Plane(origin=(sol_x, face_y(side), sol_z), x_dir=(1, 0, 0), z_dir=(0, -side, 0))
    )
    m.add(bought("solenoid", frame, "solenoid", "feedback"))
    for i, (fx, fz) in enumerate(feet):
        m.add(
            *board_screw(side, fx, fz, height, 2.0, f"strap screw {i + 1}", "feedback")
        )
        m.fit("solenoid-strap", f"strap screw {i + 1}")
        m.fit("feedback-solenoid", f"nut, strap screw {i + 1}")
    m.add(
        bought(
            "mosfet-module",
            on_face(side, mos_x, mos_z, 2.0),
            "MOSFET module",
            "feedback",
        )
    )
    m.add(*board_screw(side, mos_x - 3.5, mos_z, 2.0, 1.6, "MOSFET screw", "feedback"))
    m.fit("MOSFET module", "MOSFET screw")
    m.fit("feedback-solenoid", "nut, MOSFET screw")
    return m


@cache
def feedback_carrier(fit: Fit, kind: str) -> Module:
    if kind == "vibration":
        return _coin_carrier(
            fit,
            "feedback-vibration",
            "coin-motor",
            "motor-driver",
            (12.0, 10.0, 4.0),
            "vibration motor",
        )
    if kind == "lra":
        return _coin_carrier(
            fit, "feedback-lra", "lra", "drv2605l", (18.0, 13.0, 3.0), "LRA"
        )
    if kind == "solenoid":
        return _solenoid_carrier(fit)
    raise ValueError(kind)


# -- the Pi's retainer -----------------------------------------------------------------

RETAINER_SIDE = -1
RETAINER_POST_R = 2.0  # clear of the rails' lips below


@cache
def pi_retainer(fit: Fit) -> Module:
    """Posts from the barrel's right rails to the Pi's four mounting pads,
    so the Pi cannot leave its pegs; a window in the plate over the vents.
    In the first barrel's place."""
    from boresight_case.vendor import PI_HOLES

    side = RETAINER_SIDE
    x0, x1 = L.PI_SLED_X
    plate = carrier_plate(x0, x1 - fit.clearance, side)
    window = box(
        16.0, 62.0, face_y(side) - side * 1.0, face_y(side) + side * 3.0, -10.0, 16.0
    )
    pcb_front = L.PI_PCB_Y - 1.4  # the Pi's component side
    posts = []
    for hx, hy in PI_HOLES:
        x, z = L.PI_X0 + hx, L.PI_Z0 + hy
        length = pcb_front - fit.clearance - face_y(side)
        post = cylinder(
            (x, face_y(side) - 0.01, z), (0, 1, 0), RETAINER_POST_R, length + 0.01
        )
        tip = cylinder((x, pcb_front - 2.5, z), (0, 1, 0), 1.4, 3.0)
        posts.append(post - tip)
    shape = plate - window + union(posts)
    m = Module("pi-retainer")
    m.add(
        Printed("pi-retainer", shape, up(side), "pi-retainer", perimeters=3, infill=30)
    )
    return m


__all__ = [
    "hub",
    "button_panel",
    "feedback_carrier",
    "pi_retainer",
    "spacer",
    "SOCKETS",
    "socket",
    "socket_mouth",
    "math",
    "Sequence",
    "Z",
    "hex_location",
    "hexagon_prism",
    "teardrop",
]
