"""The board kits: what turns the shared core into an ESP32-CAM or a Pi gun.

Both kits fill the muzzle port with the standard tenon, held by the port's
own two through-bolts.

**Pi Zero 2 W.** A camera module in the muzzle port carries a Camera
Module 2 or 3 on four standoffs; the Pi sled on the last barrel's left
rails carries the Pi right behind it, its ports facing the window in the
barrel's floor. The sled's front lug holds the camera board on its
standoffs, and the retainer on the right rails holds the Pi on its pegs.
HDMI, USB and the power plug go into the Pi from below, through the
window; a clamp bar under the barrel takes any pull on the cables.

**ESP32-CAM.** A nose whose tenon fills the muzzle port carries the board
24 mm out in front of it, camera forward, antenna down. The board has no
mounting holes: it rests against stops in front, and a retainer sleeve
inside the nose's tenon, crossed by the same two bolts, presses it there.
Two plugs push onto the board's own header pins: one to the hub, one to
the debug socket and BOOT button on the nose's top.

Built for a muzzle at x = 100 (one barrel); a gun moves them along.
"""

from __future__ import annotations

from functools import cache

from build123d import Location, Part, Plane

from boresight_case import layout as L
from boresight_case.geom import NEG_X, X, Y, Z, box, cylinder, teardrop, union
from boresight_case.interfaces import Fit, Port, carrier_plate
from boresight_case.joints import barrel_port, pi_pegs, picam_pegs
from boresight_case.model import Bought, Module, Printed, bought
from boresight_case.optics import view_frustum
from boresight_case.vendor import (
    DUPONT_LEN,
    ESP32_H,
    ESP32_HEADER_PLASTIC,
    ESP32_LENS,
    ESP32_PCB,
    ESP32_PLUGS,
    ESP32_RED_LED,
    ESP32_SD,
    ESP32_W,
    LIGHT_GUIDE_LEN,
    MICRO_USB_90,
    OV2640_BODY,
    OV2640_BODY_T,
    OV2640_LENS_D,
    OV2640_LENS_L,
    PI_PORTS,
    PICAM,
    PICAM_BOARD,
    PICAM_PCB,
    esp32_pin_position,
    pi_header_pin,
)

MUZZLE = L.barrel_x(0)[1]  # 100: the kits are built here
PORT = barrel_port(0)
MODULE_UP = NEG_X  # the camera module and the nose print on their front face
SLED_UP = (0, -1, 0)  # printed on the plate's outer face
SLEEVE_UP = X  # printed standing on its rear end

# -- the Pi camera module ------------------------------------------------------------

PICAM_PCB_FRONT_X = L.PICAM_PCB_BACK_X + PICAM_PCB
FLANGE = (MUZZLE, MUZZLE + L.FLANGE_T)
FLANGE_SIZE = (L.BODY_W - 1.0, L.BODY_H - 1.0)


def picam_lens_front(model: str) -> float:
    return PICAM_PCB_FRONT_X + PICAM[model][1]


# -- the ESP32-CAM nose ----------------------------------------------------------------

BOARD_BACK_X = MUZZLE + L.NOSE_BOARD_BACK  # 124
NOSE_FRONT = MUZZLE + L.NOSE_LEN  # 136
FRONT_PLATE_T = 2.5
LENS_Y, LENS_Z = ESP32_LENS[0], -ESP32_LENS[1]  # the board turned antenna-down
OV2640_BACK_X = BOARD_BACK_X + ESP32_PCB + ESP32_SD + 0.3  # on the micro-SD slot
LENS_FRONT_X = OV2640_BACK_X + OV2640_BODY_T + OV2640_LENS_L
# The debug board: a piece of perfboard screwed up under the nose's top,
# carrying the debug socket and the BOOT button, which come out through
# the top, and the capacitor hung under it, well clear of the antenna.
DEBUG_BOARD = (MUZZLE + 12.75, -2.5)  # its centre, x and y
DEBUG_BOARD_Z = L.IN_HALF_H - 8.5  # its top face: the socket stands on it
SOCKET_X = (MUZZLE + 5.0, MUZZLE + 5.0 + 6 * 2.54)
SOCKET_Y = -1.5
BOOT_AT = (MUZZLE + 12.0, -6.5)  # x, y
DEBUG_SCREW = (MUZZLE + 12.0, 2.6)
CAPACITOR = (
    MUZZLE + 5.0,
    0.0,
    DEBUG_BOARD_Z - 1.6 - 1.0 - 3.0 - 4.2,
)  # under the screw head


def lens_front(camera: str) -> float:
    return LENS_FRONT_X if camera == "ov2640" else picam_lens_front(camera)


def lens_centre(camera: str) -> tuple[float, float, float]:
    if camera == "ov2640":
        return (LENS_FRONT_X, LENS_Y, LENS_Z)
    return (picam_lens_front(camera), 0.0, 0.0)


def frustum(camera: str, length: float = 60.0, muzzle: float = MUZZLE) -> Part:
    """The camera's view, from its lens out to `length` past the gun's front
    (the nose's, or the muzzle's)."""
    centre = lens_centre(camera)
    front = NOSE_FRONT if camera == "ov2640" else FLANGE[1]
    shape = view_frustum(camera, centre, front - centre[0] + length)
    return Location((muzzle - MUZZLE, 0, 0)) * shape


def _aperture(cameras: tuple[str, ...]) -> Part:
    """An opening that clears every camera's view, so nothing of the case
    is ever in frame."""
    return union(frustum(c, 5.0) for c in cameras)


# -- the Pi kit ----------------------------------------------------------------------


def _picam_module(fit: Fit) -> Part:
    """The tenon in the muzzle port, the front plate on the muzzle, and the
    camera's four standoffs back from the plate."""
    tenon = PORT.tenon(fit, MODULE_UP, root=False)
    fw, fh = FLANGE_SIZE
    flange = box(*FLANGE, -fw / 2, fw / 2, -fh / 2, fh / 2)
    pegs = union(p.peg(fit) for p in picam_pegs())
    housing = max(PICAM[m][0] for m in PICAM) / 2 + fit.clearance
    room = box(
        PICAM_PCB_FRONT_X, FLANGE[0] + 0.01, -housing, housing, -housing, housing
    )
    return tenon + flange + pegs - room - _aperture(tuple(PICAM))


def picam_location() -> Location:
    return Location((L.PICAM_PCB_BACK_X, 0, 0))


def pi_location() -> Location:
    """The Pi frame in the barrel: board x forward from the micro-SD end at
    PI_X0, board y up from the port edge at PI_Z0, components toward -y."""
    return Location(
        Plane(origin=(L.PI_X0, L.PI_PCB_Y, L.PI_Z0), x_dir=X, z_dir=(0, -1, 0))
    )


def _sled(fit: Fit) -> Part:
    """The plate on the left rails, the Pi's four pegs, and a lug at its
    front end that holds the camera board on its standoffs."""
    c = fit.clearance
    x0, x1 = L.PI_SLED_X
    plate = carrier_plate(x0, x1 - c, +1)
    pegs = union(p.peg(fit) for p in pi_pegs())
    face = L.plate_y(+1)[0]
    # Beside the camera's back parts, between its upper and lower pegs.
    y0 = PICAM_BOARD[1] - 1.9
    bore = L.IN_HALF_W - c - L.WALL  # past the port's mouth, only inside the tenon
    lug = box(x1 - 4.0, x1 - c + 0.01, y0, face + 0.01, -3.0, 5.5)
    tip = box(x1 - c, L.PICAM_PCB_BACK_X - c, y0, bore - 0.05, -3.0, 5.5)
    return plate + pegs + lug + tip


def _plug_at(port: str, key: str, label: str, depth: float = 0.0) -> Bought:
    """A plug from below into one of the Pi's ports: the receptacle's face
    on the Pi's port edge, the plug entering upward."""
    x = L.PI_X0 + PI_PORTS[port]
    y = L.PI_PCB_Y - 1.4 - 1.65
    z = L.PI_Z0 - 0.8 - depth
    return bought(
        key, Location(Plane(origin=(x, y, z), x_dir=X, z_dir=Z)), label, "pi-zero-2w"
    )


CLAMP_X = (72.0, 80.0)
CLAMP_Z = (L.FLOOR_Z - 9.0, L.FLOOR_Z - 5.0)  # the bar, 5 mm under the floor
CLAMP_SCREW = (76.0, 4.5)


def _clamp_bar(fit: Fit) -> Part:
    """A bar under the barrel just ahead of the window: legs at its ends
    stand on the barrel's underside, and the cables lie in the gap between."""
    x0, x1 = CLAMP_X
    z0, z1 = CLAMP_Z
    half = L.HALF_W - 1.0
    bar = box(x0, x1, -half, half, z0, z1)
    legs = union(
        box(x0, x1, y0, y1, z1 - 0.01, L.FLOOR_Z - 0.01)
        for y0, y1 in ((-half, -half + 3.0), (half - 3.0, half))
    )
    sx, sy = CLAMP_SCREW
    hole = teardrop((sx, sy, z0 - 1), Z, 1.7, z1 - z0 + 2, (1, 0, 0))
    ring = cylinder((sx, sy, z0 - 0.01), Z, 3.3, 1.7)
    return bar + legs - hole - ring


def _clamp_parts(fit: Fit) -> list[Bought]:
    from boresight_case.joints import CLAMP_FIX

    sx, sy = CLAMP_SCREW
    screw = Location(Plane(origin=(sx, sy, CLAMP_Z[0]), z_dir=Z))
    ring = Location(Plane(origin=(sx, sy, CLAMP_Z[0] + 0.85), z_dir=Z))
    nut = CLAMP_FIX.nut_location(fit, NEG_X)
    return [
        bought("m3-thumbscrew-16", screw, "clamp thumbscrew", "clamp"),
        bought("o-ring", ring, "clamp O-ring", "clamp"),
        bought("m3-nut", nut, "nut, clamp", "clamp"),
    ]


@cache
def pi_kit(fit: Fit, camera: str) -> Module:
    """The Pi kit in the first barrel: the camera module, the sled, the
    retainer, the plugs at the window and the clamp."""
    from boresight_case.parts.carriers import pi_retainer

    m = Module("pi-zero-2w")
    m.add(
        Printed(
            "camera-pi",
            _picam_module(fit),
            MODULE_UP,
            "camera",
            perimeters=3,
            infill=30,
        )
    )
    m.add(
        Printed("sled-pi-zero-2w", _sled(fit), SLED_UP, "sled", perimeters=3, infill=30)
    )
    for p in pi_retainer(fit).printed:
        m.add(p)
    m.add(Printed("cable-clamp", _clamp_bar(fit), Z, "clamp", perimeters=4, infill=40))
    m.add(bought(f"picam-{camera}", picam_location(), "camera", "camera"))
    m.add(bought("pi-zero-2w", pi_location(), "Pi Zero 2 W", "sled"))
    # The heatsink on the processor.
    from boresight_case.vendor import PI_SOC

    sx, sy, _ = PI_SOC
    soc_top = L.PI_PCB_Y - 1.4 - 3.3
    m.add(
        bought(
            "heatsink",
            Location(
                Plane(origin=(L.PI_X0 + sx, soc_top, L.PI_Z0 + sy), z_dir=(0, -1, 0))
            ),
            "heatsink",
            "sled",
        )
    )
    # The Pi signal lead: one 1x10 housing on the header's odd pins 1-19.
    hx = (pi_header_pin(1)[0] + pi_header_pin(19)[0]) / 2
    _, hy = pi_header_pin(1)
    plastic = L.PI_PCB_Y - 1.4 - 2.5
    where = Location(
        Plane(origin=(L.PI_X0 + hx, plastic, L.PI_Z0 + hy), x_dir=X, z_dir=(0, -1, 0))
    )
    m.add(bought("dupont10", where, "Pi signal plug", "sled"))
    m.fit("Pi signal plug", "Pi Zero 2 W")  # on the header's pins
    m.add(_plug_at("hdmi", "mini-hdmi-90", "HDMI plug"))
    m.add(_plug_at("usb", "micro-usb", "USB plug"))
    m.add(_plug_at("pwr", "micro-usb-90", "power plug"))
    for plug in ("HDMI plug", "USB plug", "power plug"):
        m.fit(plug, "Pi Zero 2 W")  # in its port
    m.add(*_clamp_parts(fit))
    m.fit("cable-clamp", "clamp O-ring")
    m.fit("clamp thumbscrew", "clamp O-ring")
    m.fit("barrel", "nut, clamp")
    return m


# -- the ESP32-CAM kit ---------------------------------------------------------------


def esp32_location() -> Location:
    """The board frame in the gun: its back face at BOARD_BACK_X, turned
    180 degrees about the bore so its antenna points down."""
    return Location(
        Plane(origin=(BOARD_BACK_X, 0, 0), x_dir=(1, 0, 0), z_dir=(0, 0, -1))
    )


def board_point(p) -> tuple[float, float, float]:
    """A point in the board frame, in the gun."""
    return tuple((esp32_location() * Location(tuple(p))).position)


NOSE_WALL = L.WALL


def _nose(fit: Fit) -> Part:
    """The nose: a tenon tube in the muzzle port (the retainer sleeve sits
    inside it and takes the bolts' crush), the body ahead of the muzzle,
    the front plate with the camera's pocket and aperture, the board's
    stops, and on top the debug socket's and BOOT button's openings and the
    light guide's window."""
    c = fit.clearance
    ow, oh = L.IN_W - 2 * c, L.IN_H - 2 * c
    t = L.WALL
    x0, x1 = PORT.zone
    tenon = box(x0, x1 + 0.01, -ow / 2, ow / 2, -oh / 2, oh / 2) - box(
        x0 - 1, x1 + 1, -ow / 2 + t, ow / 2 - t, -oh / 2 + t, oh / 2 - t
    )
    kw, _ = L.KEY_RIB
    tenon = tenon - box(
        x0 - 1, x1 + 1, -kw / 2 - c, kw / 2 + c, oh / 2 - t - 0.5, oh / 2 + 1
    )
    hw, hh = L.HALF_W, L.HALF_H
    body = box(MUZZLE, NOSE_FRONT, -hw, hw, -hh, hh) - box(
        MUZZLE - 1, NOSE_FRONT - FRONT_PLATE_T, -hw + t, hw - t, -hh + t, hh - t
    )
    # The tenon's root fuses it to the body behind the muzzle face.
    collar = PORT._root(fit)
    # The board's stops: ribs in front of its edges, and under and over it.
    bx = BOARD_BACK_X + ESP32_PCB + c
    stops = (
        union(
            box(
                bx,
                bx + 2.0,
                s * (ESP32_W / 2 - 1.0),
                s * (hw - t + 0.01),
                -hh + t,
                hh - t,
            )
            for s in (1, -1)
        )
        + box(
            BOARD_BACK_X - 3.0,
            bx + 2.0,
            -ESP32_W / 2 + 2,
            ESP32_W / 2 - 2,
            -hh + t - 0.01,
            -ESP32_H / 2 - c,
        )
        + box(
            BOARD_BACK_X - 3.0,
            bx + 2.0,
            -ESP32_W / 2 + 2,
            ESP32_W / 2 - 2,
            ESP32_H / 2 + c,
            hh - t + 0.01,
        )
    )
    # The camera: its body in a pocket behind the front plate that sets the
    # aim, its lens through the plate.
    s = OV2640_BODY / 2 + c
    fp = NOSE_FRONT - FRONT_PLATE_T
    block = box(
        OV2640_BACK_X - 0.2,
        fp + 0.01,
        LENS_Y - s - 1.6,
        LENS_Y + s + 1.6,
        LENS_Z - s - 1.6,
        LENS_Z + s + 1.6,
    )
    pocket = box(
        OV2640_BACK_X - 1,
        OV2640_BACK_X + OV2640_BODY_T + c,
        LENS_Y - s,
        LENS_Y + s,
        LENS_Z - s,
        LENS_Z + s,
    )
    lens = cylinder((OV2640_BACK_X, LENS_Y, LENS_Z), X, OV2640_LENS_D / 2 + c, 20)
    # The camera's flat cable leaves the pocket's bottom, down the board's
    # front to its connector at the antenna end.
    fpc = box(
        OV2640_BACK_X - 1,
        OV2640_BACK_X + 0.8,
        LENS_Y - 4.5,
        LENS_Y + 4.5,
        LENS_Z - s - 3,
        LENS_Z - s + 0.01,
    )
    # The debug board's boss, down from the top.
    dx, dy = DEBUG_SCREW
    boss = box(dx - 3.0, dx + 3.0, dy - 2.75, dy + 3.0, DEBUG_BOARD_Z, hh - t + 0.01)
    from boresight_case.vendor import M2_5

    hole_d, _, _, af, nut_h = M2_5
    nut_z = DEBUG_BOARD_Z + 2.5 + nut_h / 2
    boss_cuts = teardrop(
        (dx, dy, DEBUG_BOARD_Z - 0.5), Z, hole_d / 2, 7.0, MODULE_UP
    ) + box(
        dx - af / 2 - c,
        dx + 3.5,
        dy - af / 2 - c,
        dy + af / 2 + c,
        nut_z - nut_h / 2 - c,
        nut_z + nut_h / 2 + c,
    )
    shape = tenon + body + collar + stops + block + boss
    cuts = [
        pocket,
        lens,
        fpc,
        _aperture(("ov2640",)),
        _top_openings(fit),
        PORT.tenon_cuts(MODULE_UP),
        boss_cuts,
    ]
    return shape - union(cuts)


def _top_openings(fit: Fit) -> Part:
    """The debug socket's contacts, the BOOT button's stem and the light
    guide, out through the nose's top."""
    c = fit.clearance
    top = L.HALF_H
    sx0, sx1 = SOCKET_X
    socket = box(
        sx0 + 0.3,
        sx1 - 0.3,
        SOCKET_Y - 0.75,
        SOCKET_Y + 0.75,
        top - L.WALL - 0.5,
        top + 0.5,
    )
    bx, by = BOOT_AT
    boot = teardrop((bx, by, top - L.WALL - 0.5), Z, 2.0 + c, L.WALL + 1, MODULE_UP)
    gx, gy, gz = led_point()
    guide = teardrop((gx, gy, gz), Z, 1.1, top - gz + 1, MODULE_UP)
    return socket + boot + guide


def led_point() -> tuple[float, float, float]:
    return board_point(ESP32_RED_LED)


def _sleeve(fit: Fit) -> Part:
    """The retainer sleeve: a ring inside the nose's tenon with the bolts'
    crush tubes, and two prongs forward along its lower side walls to the
    board's back, beside the header rows."""
    c = fit.clearance
    t = L.WALL
    ow = L.IN_W - 2 * c - 2 * t - 2 * c  # inside the nose's tenon
    oh = L.IN_H - 2 * c - 2 * t - 2 * c
    w = 2.0
    x0, x1 = PORT.zone
    ring = box(x0, x1, -ow / 2, ow / 2, -oh / 2, oh / 2) - box(
        x0 - 1, x1 + 1, -ow / 2 + w, ow / 2 - w, -oh / 2 + w, oh / 2 - w
    )
    kw, _ = L.KEY_RIB
    ring = ring - box(
        x0 - 1, x1 + 1, -kw / 2 - c, kw / 2 + c, oh / 2 - w - 0.5, oh / 2 + 1
    )
    tubes = union(
        b.crush_tube(-ow / 2 + w - 0.01, ow / 2 - w + 0.01, SLEEVE_UP)
        for b in PORT.bolts
    )
    back = BOARD_BACK_X - c
    prongs = union(
        box(x1 - 0.01, back, s * (ow / 2 - w), s * ow / 2, -oh / 2, -4.0)
        for s in (1, -1)
    )
    holes = union(b.hole(-30, 30, SLEEVE_UP) for b in PORT.bolts)
    return ring + tubes + prongs - holes


@cache
def esp32_kit(fit: Fit) -> Module:
    m = Module("esp32-cam")
    m.add(
        Printed(
            "nose-esp32-cam", _nose(fit), MODULE_UP, "nose", perimeters=3, infill=30
        )
    )
    m.add(
        Printed("nose-sleeve", _sleeve(fit), SLEEVE_UP, "nose", perimeters=3, infill=40)
    )
    m.add(bought("esp32-cam", esp32_location(), "ESP32-CAM", "nose"))
    # Its flat cable leaves its bottom, down to the connector.
    cam = Location((OV2640_BACK_X, LENS_Y, LENS_Z))
    m.add(bought("ov2640", cam, "camera", "nose"))
    m.fit("ESP32-CAM", "camera")  # its ribbon lies on the board's front
    for plug, (row, first, last) in ESP32_PLUGS.items():
        lo = esp32_pin_position(row, first)
        hi = esp32_pin_position(row, last)
        mid = tuple((a + b) / 2 for a, b in zip(lo, hi, strict=True))
        # The housing: ways along the row (the board's z), outward along -x.
        x, y, z = board_point(mid)
        where = Location(Plane(origin=(x, y, z), x_dir=(0, 0, 1), z_dir=NEG_X))
        label = f"{plug} plug"
        m.add(bought("dupont6", where, label, "nose"))
        m.fit(label, "ESP32-CAM")  # the housing goes over the pins
    # The debug board under the nose's top: the socket and BOOT on it, the
    # capacitor hung under it.
    bx0, by0 = DEBUG_BOARD
    board = Location(Plane(origin=(bx0, by0, DEBUG_BOARD_Z - 1.6), x_dir=X, z_dir=Z))
    m.add(bought("perfboard-small", board, "debug board", "nose"))
    sx = (SOCKET_X[0] + SOCKET_X[1]) / 2
    socket = Location(Plane(origin=(sx, SOCKET_Y, DEBUG_BOARD_Z), x_dir=X, z_dir=Z))
    m.add(bought("header-6f", socket, "debug socket", "nose"))
    bx, by = BOOT_AT
    m.add(bought("tact-13", Location((bx, by, DEBUG_BOARD_Z)), "BOOT button", "nose"))
    for part in ("debug socket", "BOOT button"):
        m.fit("debug board", part)  # soldered through it
    dx, dy = DEBUG_SCREW
    m.add(
        bought(
            "m2.5x6",
            Location(Plane(origin=(dx, dy, DEBUG_BOARD_Z - 1.6), z_dir=(0, 0, -1))),
            "debug board screw",
            "nose",
        )
    )
    from boresight_case.vendor import M2_5

    nut_z = DEBUG_BOARD_Z + 2.5 + M2_5[4] / 2
    m.add(
        bought("m2.5-nut", Location((dx, dy, nut_z)), "nut, debug board screw", "nose")
    )
    m.fit("debug board", "debug board screw")
    m.fit("nose-esp32-cam", "nut, debug board screw")
    m.add(bought("capacitor", Location(CAPACITOR), "capacitor", "nose"))
    gx, gy, gz = led_point()
    m.add(bought("light-guide", Location((gx, gy, gz + 1.0)), "light guide", "nose"))
    m.fit("ESP32-CAM", "light guide")  # it stands on the LED, among the board's parts
    return m


__all__ = [
    "esp32_kit",
    "pi_kit",
    "frustum",
    "lens_front",
    "Y",
    "DUPONT_LEN",
    "ESP32_HEADER_PLASTIC",
    "LIGHT_GUIDE_LEN",
    "MICRO_USB_90",
    "Port",
]
