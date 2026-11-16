"""Purchased parts, as envelopes: the space each one needs, not its detail.

Every printed pocket, peg and clearance is cut from these, so a part from
another vendor means editing one entry here. Each entry records where its
dimensions came from: a published mechanical drawing ("datasheet"), a
caliper measurement ("caliper"), or the typical listing dimensions of a
part sold by many vendors ("listing"), which is a guess until measured.

Each builder returns the envelope in the part's own frame, described in
its docstring; the modules place it.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from build123d import Part

from boresight_case.geom import X, Y, Z, box, cylinder, union

# -- the screws and nuts every joint uses ------------------------------------

M3_CLEAR = 3.4  # clearance hole diameter
M3_HEAD_D = 5.5
M3_HEAD_H = 3.0
M3_HEAD_CBORE = 6.2  # counterbore for the head
M3_NUT_AF = 5.5
M3_NUT_H = 2.4
M3_NYLOC_H = 4.0  # a nylon-insert lock nut
M3_INSERT_HOLE = 4.0  # hole for a 4.6 mm M3 heat-set insert
M3_INSERT_LEN = 5.7
SCREW_LENGTHS = (8.0, 12.0)


@dataclass(frozen=True)
class VendorPart:
    key: str
    # The bill-of-materials line: what to buy.
    spec: str
    source: str
    build: Callable[[], Part]
    metal: bool = False
    # A board, camera, cell, switch or wire: no skin may touch it.
    functional: bool = True
    dims: dict[str, float] = field(default_factory=dict)


# -- ESP32-CAM ---------------------------------------------------------------

ESP32_W = 27.0  # across (y)
ESP32_H = 40.5  # tall (z); antenna at +z
ESP32_PCB = 1.6
ESP32_FRONT = 3.3  # ESP32-S module shield above the PCB
ESP32_BACK = 2.0  # PSRAM, regulator, SD slot, LED below the PCB
ESP32_HEADER_ROW_Y = 11.43  # rows at +-0.45 in
ESP32_HEADER_Z0 = -18.9  # lowest pin, 2.54 mm pitch upward
ESP32_HEADER_PLASTIC = 2.5
ESP32_PIN_LEN = 6.0
DUPONT_LEN = 14.5  # housing, from the header plastic outward
# Header pins (row, index from the bottom) the case wires to. Row +1 is the
# row at +y when the board's front faces +x.
ESP32_PINS = {
    "5V": (+1, 0),
    "GND": (+1, 1),
    "IO13": (+1, 3),
    "GND2": (-1, 3),
}
# The PCB antenna, on the ESP32-S module's far end (frame below).
ESP32_ANTENNA = (0.0, ESP32_PCB + ESP32_FRONT, -9.0, 9.0, 14.25, 20.25)
# The red status LED (GPIO33) on the back and the white flash LED (GPIO4)
# on the front. Positions are estimates until a board is measured.
ESP32_RED_LED = (-1.0, 7.5, -15.0)
ESP32_FLASH_LED = (ESP32_PCB + 0.8, -7.0, -15.5)


def esp32_pin_position(name: str) -> tuple[float, float, float]:
    """Where a used header pin meets the header plastic (board frame)."""
    row, index = ESP32_PINS[name]
    return (
        -ESP32_HEADER_PLASTIC,
        row * ESP32_HEADER_ROW_Y,
        ESP32_HEADER_Z0 + 2.54 * index,
    )


def _esp32_cam() -> Part:
    """Board frame: the PCB's back face at x=0, front (camera side) toward +x,
    centred on y=0, z=0, antenna end at +z."""
    w, h = ESP32_W / 2, ESP32_H / 2
    pcb = box(0, ESP32_PCB, -w, w, -h, h)
    module = box(ESP32_PCB, ESP32_PCB + ESP32_FRONT, -9, 9, h - 25.5, h)
    front_parts = box(ESP32_PCB, ESP32_PCB + 2.5, -w + 1, w - 1, -h + 1, h - 25.5)
    back_parts = box(-ESP32_BACK, 0, -8.5, 8.5, -h + 1, h - 2)
    rows = []
    for row in (-1, 1):
        y = row * ESP32_HEADER_ROW_Y
        z0, z1 = ESP32_HEADER_Z0 - 1.27, ESP32_HEADER_Z0 + 7 * 2.54 + 1.27
        rows.append(box(-ESP32_HEADER_PLASTIC, 0, y - 1.27, y + 1.27, z0, z1))
        rows.append(
            box(
                -ESP32_HEADER_PLASTIC - ESP32_PIN_LEN,
                -ESP32_HEADER_PLASTIC,
                y - 0.32,
                y + 0.32,
                z0 + 0.95,
                z1 - 0.95,
            )
        )
    return union([pcb, module, front_parts, back_parts, *rows])


# -- OV2640 camera (on the ESP32-CAM's short FPC) ------------------------------

OV2640_BODY = 8.5
OV2640_BODY_T = 2.2
OV2640_LENS_D = 7.0
OV2640_LENS_L = 3.5


def _ov2640() -> Part:
    """Camera frame: lens axis along +x through y=0, z=0; the body's back at
    x=0 and the lens front at x=5.7. The FPC leaves the body's -z edge."""
    s = OV2640_BODY / 2
    body = box(0, OV2640_BODY_T, -s, s, -s, s)
    lens = cylinder((OV2640_BODY_T, 0, 0), X, OV2640_LENS_D / 2, OV2640_LENS_L)
    fpc = box(0, 0.4, -4, 4, -s - 6, -s)
    return union([body, lens, fpc])


# -- Raspberry Pi Zero 2 W ---------------------------------------------------

PI_L = 65.0
PI_W = 30.0
PI_PCB = 1.4
PI_TOP = 3.3  # tallest top-side part (mini-HDMI)
PI_BOTTOM = 1.2
PI_HOLES = ((3.5, 3.5), (61.5, 3.5), (3.5, 26.5), (61.5, 26.5))
PI_HOLE_D = 2.75
PI_HEADER_PLASTIC = 2.5
PI_HEADER_PIN_TOP = PI_PCB + 8.5
PI_USB_DATA_X = 41.4
PI_SOC = (30.0, 15.5, 14.0)  # centre x, centre y, size
SD_CARD_PROTRUDE = 2.5


def pi_header_pin(n: int) -> tuple[float, float]:
    """(x, y) of header pin `n` in the Pi frame: odd pins in the inner row."""
    index = (n - 1) // 2
    x = PI_L / 2 - 19 * 2.54 / 2 + index * 2.54
    y = 26.5 - 1.27 if n % 2 else 26.5 + 1.27
    return (x, y)


def _pi_zero() -> Part:
    """Pi frame: the PCB's bottom face at z=0 in the x-y plane; x from the
    micro-SD end (0) to the camera connector end (65); y from the port edge
    (0) to the header edge (30)."""
    pcb = box(0, PI_L, 0, PI_W, 0, PI_PCB)
    top = box(1, PI_L - 1, 1, PI_W - 5, PI_PCB, PI_PCB + PI_TOP)
    bottom = box(6, PI_L - 6, 1, PI_W - 1, -PI_BOTTOM, 0)
    hx = PI_L / 2
    header = box(
        hx - 25.4,
        hx + 25.4,
        26.5 - 2.54,
        26.5 + 2.54,
        PI_PCB,
        PI_PCB + PI_HEADER_PLASTIC,
    )
    pins = box(hx - 24.5, hx + 24.5, 26.5 - 1.6, 26.5 + 1.6, PI_PCB, PI_HEADER_PIN_TOP)
    sd = box(-SD_CARD_PROTRUDE, 12, 10.5, 22.5, PI_PCB, PI_PCB + 1.4)
    ports = [
        box(x - w / 2, x + w / 2, -0.8, 5.0, PI_PCB, PI_PCB + t)
        for x, w, t in ((12.4, 11.2, 3.3), (PI_USB_DATA_X, 7.5, 2.6), (54.0, 7.5, 2.6))
    ]
    cam = box(PI_L - 5.0, PI_L + 0.5, 6.5, 23.5, PI_PCB, PI_PCB + 1.3)
    board = union([pcb, top, bottom, header, pins, sd, cam, *ports])
    # The mounting holes, in their 6 mm component-free pads.
    for hx, hy in PI_HOLES:
        pad = cylinder(
            (hx, hy, -PI_BOTTOM - 0.1), Z, 3.0, PI_BOTTOM + PI_TOP + 0.2
        ) - cylinder((hx, hy, -0.1), Z, 3.1, PI_PCB + 0.2)
        board = board - pad - cylinder((hx, hy, -1), Z, PI_HOLE_D / 2, PI_PCB + 2)
    return board


# -- Raspberry Pi Camera Modules 2 and 3 --------------------------------------

PICAM_HOLES = ((-10.5, 7.5), (10.5, 7.5), (-10.5, -5.0), (10.5, -5.0))  # (y, z)
PICAM_HOLE_D = 2.2
PICAM_PCB = 1.0
PICAM_BOARD = (-12.5, 12.5, -14.5, 9.5)  # y0, y1, z0, z1 about the lens axis
# (lens housing square, height above the PCB, horizontal and vertical FOV)
PICAM = {
    "cm2": (8.5, 8.0, 62.2, 48.8),
    "cm3": (11.0, 10.5, 66.0, 41.0),
}


def _picam(model: str) -> Callable[[], Part]:
    def build() -> Part:
        """Camera frame: lens axis +x through y=0, z=0; the PCB's back face at
        x=0. The 15-way connector is on the back at the bottom edge."""
        square, height, _, _ = PICAM[model]
        y0, y1, z0, z1 = PICAM_BOARD
        pcb = box(0, PICAM_PCB, y0, y1, z0, z1)
        lens = box(
            PICAM_PCB,
            PICAM_PCB + height,
            -square / 2,
            square / 2,
            -square / 2,
            square / 2,
        )
        parts_back = box(-1.2, 0, y0 + 2, y1 - 2, z0 + 5.5, z1 - 4)
        connector = box(-2.6, 0, -10.3, 10.3, z0, z0 + 5.0)
        cam = union([pcb, lens, parts_back, connector])
        for hy, hz in PICAM_HOLES:
            cam = cam - cylinder((-2.0, hy, hz), X, 2.25, 2.0 - 0.01)
            cam = cam - cylinder((-1, hy, hz), X, PICAM_HOLE_D / 2, PICAM_PCB + 2)
        return cam

    return build


# -- power ----------------------------------------------------------------------

# (length along the cells, width, height); wires leave the -length end.
HOLDERS = {
    "aa": (58.0, 31.0, 31.0),
    "aaa": (52.0, 23.0, 23.0),
    "18650": (77.0, 21.0, 19.5),
}


def _holder(kind: str) -> Callable[[], Part]:
    def build() -> Part:
        """Holder frame: cells along +x from x=0, centred on y=0, z=0."""
        length, width, height = HOLDERS[kind]
        return box(0, length, -width / 2, width / 2, -height / 2, height / 2)

    return build


TP4056 = (28.0, 17.0, 1.6)  # length (port at +x), width, PCB thickness
TP4056_PORT = (9.0, 3.3, 7.5)  # width, height, depth of the USB-C receptacle
TP4056_LED_X = 20.0  # the charge LEDs, measured from the far end


def _tp4056() -> Part:
    """TP4056 USB-C charger with protection: PCB bottom at z=0, the USB-C port
    at the +x end, protruding 1 mm past the board."""
    length, width, t = TP4056
    pcb = box(0, length, -width / 2, width / 2, 0, t)
    parts = box(2, length - 8, -width / 2 + 1, width / 2 - 1, t, t + 1.8)
    pw, ph, pd = TP4056_PORT
    port = box(length - pd + 1.0, length + 1.0, -pw / 2, pw / 2, t, t + ph)
    return union([pcb, parts, port])


BUCK_BOOST = (21.0, 13.0, 5.0)


def _buck_boost() -> Part:
    """Regulator frame: a board up to 21 x 13 x 5 mm, centred, lying flat."""
    length, width, height = BUCK_BOOST
    pcb = box(-length / 2, length / 2, -width / 2, width / 2, 0, 1.6)
    # Parts keep about a millimetre off the edges, where holders grip it.
    parts = box(
        -length / 2 + 1, length / 2 - 1, -width / 2 + 1, width / 2 - 1, 1.6, height
    )
    return pcb + parts


ROCKER_CUTOUT = (13.0, 9.0)
ROCKER_BEZEL = (15.0, 10.5, 4.0)
ROCKER_DEPTH = 12.0


def _rocker() -> Part:
    """Snap-in mini rocker: the panel's outer face at z=0, bezel above it,
    body and terminals below; 13 mm along x, 9 mm along y."""
    bx, by, bz = ROCKER_BEZEL
    cx, cy = ROCKER_CUTOUT
    bezel = box(-bx / 2, bx / 2, -by / 2, by / 2, 0, bz)
    body = box(-cx / 2, cx / 2, -cy / 2, cy / 2, -ROCKER_DEPTH, 0)
    return bezel + body


CONTACT_PLATE = (10.0, 10.0, 0.5)
SPRING_COMPRESSED = 3.5


def _spring_contact() -> Part:
    """Battery spring contact, compressed: its plate on z=0, spring below
    toward -z."""
    sx, sy, sz = CONTACT_PLATE
    plate = box(-sx / 2, sx / 2, -sy / 2, sy / 2, 0, sz)
    spring = cylinder((0, 0, 0), (0, 0, -1), 4.0, SPRING_COMPRESSED)
    return plate + spring


def _flat_contact() -> Part:
    """Battery flat contact plate on z=0, facing +z."""
    sx, sy, sz = CONTACT_PLATE
    return box(-sx / 2, sx / 2, -sy / 2, sy / 2, 0, sz)


# -- switches ---------------------------------------------------------------------

MX_CUTOUT = 14.0
MX_PLATE = 1.5
MX_ABOVE = 6.6  # housing above the plate's top face
MX_STEM_TOP = 11.6  # stem top above the plate at rest
MX_BELOW = 5.0
MX_PINS = 3.3
MX_ACTUATION = 2.0
MX_TRAVEL = 4.0


def _mx() -> Part:
    """MX-footprint switch: the plate's top face at x=0, stem toward +x."""
    housing = box(0, MX_ABOVE, -7.8, 7.8, -7.8, 7.8)
    stem = box(MX_ABOVE, MX_STEM_TOP, -2.75, 2.75, -2.75, 2.75)
    below = box(-MX_PLATE - MX_BELOW, 0, -7.0, 7.0, -7.0, 7.0)
    pins = box(
        -MX_PLATE - MX_BELOW - MX_PINS, -MX_PLATE - MX_BELOW, -5.0, 5.0, -2.0, 4.0
    )
    return union([housing, stem, below, pins])


MICRO = (20.0, 6.4, 10.2)  # length, thickness, height
MICRO_HOLE_PITCH = 9.5
MICRO_HOLE_D = 2.3
MICRO_HOLE_Z = 2.9  # hole centres above the body's bottom edge
# The hinge lever: hinged near one end of the body's top edge, its tip
# 20 mm along. Travel figures are at the tip.
MICRO_HINGE_X = -9.0
MICRO_LEVER_LEN = 20.0
MICRO_LEVER_FREE = 2.6  # the tip above the body's top edge at rest
MICRO_PRETRAVEL = 1.6  # tip travel from rest to the operating point
MICRO_OVERTRAVEL = 0.8  # further tip travel before the plunger bottoms


def micro_lever_height(x: float) -> float:
    """The lever's surface above the body's top edge at rest, at `x` along
    the switch (switch frame)."""
    return 0.3 + (MICRO_LEVER_FREE - 0.3) * (x - MICRO_HINGE_X) / MICRO_LEVER_LEN


def micro_travel_scale(x: float) -> float:
    """Travel at `x` along the lever as a fraction of the tip's."""
    return (x - MICRO_HINGE_X) / MICRO_LEVER_LEN


def _microswitch() -> Part:
    """Lever microswitch: body from z=0 (pins edge) to z=10.2 (lever edge),
    x along its length centred, y its thickness centred; the lever rises
    from its hinge at x=-9 to its tip at x=+11. Holes for pegs at x=+-4.75."""
    from boresight_case.geom import prism

    length, t, height = MICRO
    body = box(-length / 2, length / 2, -t / 2, t / 2, 0, height)
    for hx in (-MICRO_HOLE_PITCH / 2, MICRO_HOLE_PITCH / 2):
        body = body - cylinder((hx, -t, MICRO_HOLE_Z), Y, MICRO_HOLE_D / 2, 2 * t)
    tip = MICRO_HINGE_X + MICRO_LEVER_LEN
    pts = [
        (MICRO_HINGE_X, height - 0.01),
        (tip, height - 0.01),
        (tip, height + MICRO_LEVER_FREE),
        (MICRO_HINGE_X, height + 0.3),
    ]
    lever = prism((0, 2.0, 0), (1, 0, 0), (0, 0, 1), pts, 4.0)
    pins = box(-8.0, 8.0, -0.5, 0.5, -3.5, 0)
    return union([body, lever, pins])


# -- connectors, wires and small parts --------------------------------------------

JST_XH2 = (5.9, 5.75, 9.6)


def _jst_xh2() -> Part:
    """JST-XH 2-way plug and header, mated: mating axis along +z from z=0,
    with 8 mm of wire bend room beyond."""
    w, d, h = JST_XH2
    return box(-w / 2, w / 2, -d / 2, d / 2, 0, h + 8.0)


def _dupont(n: int) -> Callable[[], Part]:
    def build() -> Part:
        """Dupont housing of `n` ways on 2.54 mm pins: from the header plastic
        at z=0 outward along +z, with 6 mm of wire bend room; ways along x."""
        w = 2.54 * n
        return box(-w / 2, w / 2, -1.3, 1.3, 0, DUPONT_LEN + 6.0)

    return build


MICRO_USB_90 = (11.0, 7.6, 6.0)  # head along the cable, width, thickness
CABLE_D = 4.0


def _micro_usb_90() -> Part:
    """90-degree micro-USB plug: the receptacle face at z=0, plug entering
    along +z; the head turns the cable toward -x."""
    length, width, t = MICRO_USB_90
    tongue = box(-3.75, 3.75, -1.3, 1.3, 0, 5.5)
    head = box(-length + 3.5, 3.5, -width / 2, width / 2, -t, 0)
    return tongue + head


def _capacitor() -> Part:
    """470-1000 uF radial capacitor lying along +x from x=0."""
    return cylinder((0, 0, 0), X, 4.0, 13.0)


def _heatsink() -> Part:
    """14 x 14 x 6 mm stick-on heatsink on z=0."""
    return box(-7, 7, -7, 7, 0, 6)


def _led5() -> Part:
    """5 mm LED: its flange's back at z=0, dome toward +z."""
    return cylinder((0, 0, -1.0), Z, 2.9, 1.0) + cylinder((0, 0, 0), Z, 2.5, 7.6)


def _pivot_pin() -> Part:
    """1.75 mm filament, 22 mm, along +y from y=0."""
    return cylinder((0, 0, 0), Y, 0.875, 22.0)


def _light_guide() -> Part:
    """Clear 1.75 mm filament, 45 mm, along +z from z=0."""
    return cylinder((0, 0, 0), Z, 0.875, 45.0)


SPRING = (6.0, 18.0, 9.0)  # outside diameter, free length, installed length


def _spring() -> Part:
    """Return spring at its installed length along +x from x=0."""
    return cylinder((0, 0, 0), X, SPRING[0] / 2, SPRING[2])


def _screw(length: float) -> Callable[[], Part]:
    def build() -> Part:
        """M3 socket-head screw: the head's underside at z=0, shank toward -z."""
        head = cylinder((0, 0, 0), Z, M3_HEAD_D / 2, M3_HEAD_H)
        shank = cylinder((0, 0, 0), (0, 0, -1), 1.5, length)
        return head + shank

    return build


def _nut() -> Part:
    """M3 hex nut centred on the origin, axis z."""
    from boresight_case.geom import hexagon_prism

    # With its hole, so a screw through it is not an overlap.
    return hexagon_prism((0, 0, 0), Z, M3_NUT_AF, M3_NUT_H) - cylinder(
        (0, 0, -M3_NUT_H), Z, 1.52, 2 * M3_NUT_H
    )


def _nyloc() -> Part:
    """M3 nylon-insert lock nut centred on the origin, axis z."""
    from boresight_case.geom import hexagon_prism

    return hexagon_prism((0, 0, 0), Z, M3_NUT_AF, M3_NYLOC_H) - cylinder(
        (0, 0, -M3_NYLOC_H), Z, 1.52, 2 * M3_NYLOC_H
    )


def _insert() -> Part:
    """M3 heat-set insert, its top face at z=0, body toward -z."""
    return cylinder((0, 0, 0), (0, 0, -1), 2.3, M3_INSERT_LEN) - cylinder(
        (0, 0, 1), (0, 0, -1), 1.52, M3_INSERT_LEN + 2
    )


VENDOR: dict[str, VendorPart] = {
    p.key: p
    for p in (
        VendorPart(
            "esp32-cam",
            "AI-Thinker ESP32-CAM (27 x 40.5 mm) with header pins",
            "datasheet: AI-Thinker ESP32-CAM product specification (outline); "
            "header and LED positions are estimates",
            _esp32_cam,
            metal=True,
        ),
        VendorPart(
            "ov2640",
            "OV2640 camera module (comes with the ESP32-CAM)",
            "listing: 8.5 mm module, 66 degree lens",
            _ov2640,
            dims={
                "hfov": 56.0,
                "vfov": 43.0,
                "lens_front": OV2640_BODY_T + OV2640_LENS_L,
            },
        ),
        VendorPart(
            "pi-zero-2w",
            "Raspberry Pi Zero 2 W with a 2x20 header soldered",
            "datasheet: Raspberry Pi Zero 2 W mechanical drawing",
            _pi_zero,
            metal=True,
        ),
        VendorPart(
            "picam-cm2",
            "Raspberry Pi Camera Module 2",
            "datasheet: Camera Module 2 mechanical drawing",
            _picam("cm2"),
            dims={
                "hfov": PICAM["cm2"][2],
                "vfov": PICAM["cm2"][3],
                "lens_front": PICAM_PCB + PICAM["cm2"][1],
            },
        ),
        VendorPart(
            "picam-cm3",
            "Raspberry Pi Camera Module 3 (standard lens, not Wide)",
            "datasheet: Camera Module 3 mechanical drawing",
            _picam("cm3"),
            dims={
                "hfov": PICAM["cm3"][2],
                "vfov": PICAM["cm3"][3],
                "lens_front": PICAM_PCB + PICAM["cm3"][1],
            },
        ),
        VendorPart(
            "holder-aa",
            "4 x AA battery holder, 2 x 2 back-to-back, with leads",
            "listing: typical 2 x 2 AA holder, about 58 x 31 x 31 mm",
            _holder("aa"),
            metal=True,
        ),
        VendorPart(
            "holder-aaa",
            "4 x AAA battery holder, 2 x 2 back-to-back, with leads",
            "listing: typical 2 x 2 AAA holder, about 52 x 23 x 23 mm",
            _holder("aaa"),
            metal=True,
        ),
        VendorPart(
            "holder-18650",
            "1 x 18650 battery holder with leads, for a protected button-top cell "
            "up to 70 mm",
            "listing: typical single 18650 holder, about 77 x 21 x 19.5 mm",
            _holder("18650"),
            metal=True,
        ),
        VendorPart(
            "tp4056",
            "TP4056 USB-C Li-ion charger module with DW01 protection (28 x 17 mm)",
            "listing: typical TP4056 USB-C protected module",
            _tp4056,
            metal=True,
        ),
        VendorPart(
            "buck-boost",
            "Buck-boost 5 V regulator module, 1 A, input 2.7-6.5 V, "
            "up to 21 x 13 x 5 mm "
            "(e.g. Pololu S9V11F5)",
            "datasheet: Pololu S9V11F5 (11.4 x 15.2 mm); pocket sized for "
            "generic modules",
            _buck_boost,
            metal=True,
        ),
        VendorPart(
            "rocker",
            "Snap-in mini rocker switch, SPST, 13 x 9 mm panel cut-out (KCD11)",
            "listing: KCD11 mini rocker",
            _rocker,
            functional=False,
        ),
        VendorPart(
            "spring-contact",
            "Battery spring contact, 10 x 10 mm plate (AA type)",
            "listing: typical AA spring contact",
            _spring_contact,
            metal=True,
        ),
        VendorPart(
            "flat-contact",
            "Battery flat contact plate, 10 x 10 mm (AA type)",
            "listing: typical AA flat contact",
            _flat_contact,
            metal=True,
        ),
        VendorPart(
            "mx-switch",
            "Plate-mount switch with the MX footprint (14 mm cut-out)",
            "datasheet: Cherry MX mechanical drawing",
            _mx,
        ),
        VendorPart(
            "microswitch",
            "Lever microswitch, 20 x 10 x 6.4 mm, holes 9.5 mm apart "
            "(KW11 / SS-5GL type)",
            "datasheet: Omron SS-5GL outline",
            _microswitch,
        ),
        VendorPart(
            "jst-xh2",
            "JST-XH 2-way plug and header pair, crimped",
            "datasheet: JST XH series",
            _jst_xh2,
        ),
        VendorPart(
            "dupont1",
            "Dupont 1-way female housing and crimp",
            "listing: 2.54 mm Dupont housing",
            _dupont(1),
        ),
        VendorPart(
            "dupont3",
            "Dupont 3-way female housing and crimps",
            "listing: 2.54 mm Dupont housing",
            _dupont(3),
        ),
        VendorPart(
            "micro-usb-90",
            "USB cable, micro-USB 90-degree (left/right angle) plug to the "
            "host's plug, 2 m",
            "listing: typical 90-degree micro-USB plug",
            _micro_usb_90,
        ),
        VendorPart(
            "capacitor",
            "470-1000 uF 10 V radial electrolytic capacitor, up to 8 x 13 mm",
            "listing: 8 mm radial can",
            _capacitor,
        ),
        VendorPart(
            "heatsink",
            "Stick-on heatsink, up to 14 x 14 x 6 mm",
            "listing: typical Pi heatsink",
            _heatsink,
            metal=True,
        ),
        VendorPart(
            "led5",
            "5 mm LED and a 330 ohm resistor",
            "datasheet: T-1 3/4 LED outline",
            _led5,
        ),
        VendorPart(
            "light-guide",
            "Clear 1.75 mm filament, 45 mm (the status light guide)",
            "caliper: 1.75 mm filament",
            _light_guide,
        ),
        VendorPart(
            "pivot-pin",
            "1.75 mm filament, 22 mm (the trigger's pivot pin)",
            "caliper: 1.75 mm filament",
            _pivot_pin,
        ),
        VendorPart(
            "spring",
            "Compression spring, outside diameter up to 6 mm, free length 15-20 mm "
            "(a ballpoint pen spring usually fits)",
            "listing: ballpoint pen spring",
            _spring,
            metal=True,
        ),
        VendorPart(
            "m3x8",
            "M3 x 8 socket-head screw",
            "datasheet: ISO 4762",
            _screw(8.0),
            metal=True,
            functional=False,
        ),
        VendorPart(
            "m3x12",
            "M3 x 12 socket-head screw",
            "datasheet: ISO 4762",
            _screw(12.0),
            metal=True,
            functional=False,
        ),
        VendorPart(
            "m3-nut",
            "M3 hex nut",
            "datasheet: ISO 4032",
            _nut,
            metal=True,
            functional=False,
        ),
        VendorPart(
            "m3-nyloc",
            "M3 nylon-insert lock nut (holds the trigger's stop screw where set)",
            "datasheet: ISO 10511",
            _nyloc,
            metal=True,
            functional=False,
        ),
        VendorPart(
            "m3-insert",
            "M3 heat-set insert, 4.6 mm outside, 5.7 mm long",
            "listing: typical M3 x 5.7 brass insert",
            _insert,
            metal=True,
            functional=False,
        ),
    )
}

# Cables and wire are bought by length and bend where they must; the bill
# of materials lists them, and the checks model only their plugs.
CONSUMABLES = {
    "pi-ribbon": "Pi Zero camera cable (22-way to 15-way), 150 mm",
    "hookup-wire": "24 AWG stranded hook-up wire, about 1 m in two colours",
    "usb-tether-esp32": "USB cable to cut for its 5 V and GND wires, 2 m",
}


def fov_half_angles(camera: str) -> tuple[float, float]:
    """Half the horizontal and vertical field of view, in radians."""
    dims = VENDOR["ov2640" if camera == "ov2640" else f"picam-{camera}"].dims
    return (math.radians(dims["hfov"] / 2), math.radians(dims["vfov"] / 2))


__all__ = ["VENDOR", "VendorPart", "Y"]
