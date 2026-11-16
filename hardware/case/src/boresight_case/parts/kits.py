"""The board kits: what turns the shared core into an ESP32-CAM or a Pi gun.

Both kits share the camera bulkhead's body: a keyed plug that slides into
the muzzle, a flange that stops it there, and a tail under the board where
one screw from below holds it. The ESP32-CAM kit's bulkhead carries the
whole board, camera forward; the Pi kit's carries a Camera Module on pegs,
and a sled carries the Pi in the receiver.
"""

from __future__ import annotations

from functools import cache

from build123d import Location, Part, Plane

from boresight_case import layout as L
from boresight_case.geom import NEG_X, X, Y, Z, box, cylinder, teardrop, union
from boresight_case.interfaces import Fit
from boresight_case.joints import BULKHEAD_SCREW, BULKHEAD_SLIDE, pi_pegs, picam_pegs
from boresight_case.model import Module, Printed, bought
from boresight_case.optics import view_frustum
from boresight_case.vendor import (
    ESP32_PCB,
    ESP32_PINS,
    ESP32_W,
    OV2640_BODY,
    OV2640_BODY_T,
    OV2640_LENS_D,
    OV2640_LENS_L,
    PI_SOC,
    PI_USB_DATA_X,
    PICAM,
    PICAM_BOARD,
    PICAM_PCB,
    esp32_pin_position,
    pi_header_pin,
)

BULKHEAD_UP = NEG_X  # printed on its flange
SLED_UP = (0, -1, 0)  # printed on the plate's outer face

# The ESP32-CAM: its camera's lens front just inside the flange's face, the
# board as close behind the camera as its module allows.
OV2640_BACK_X = L.LENS_FRONT_X - OV2640_BODY_T - OV2640_LENS_L
ESP32_FRONT_X = OV2640_BACK_X - 0.3  # the ESP32-S module's shield
ESP32_BACK_X = ESP32_FRONT_X - 3.3 - ESP32_PCB  # the board frame's origin
CAPACITOR = (74.0, -5.0, -16.25)  # its can's back end, centre
LIGHT_GUIDE = (88.2, 7.5)
PICAM_PCB_FRONT_X = L.PICAM_PCB_BACK_X + PICAM_PCB


def picam_lens_front(model: str) -> float:
    return PICAM_PCB_FRONT_X + PICAM[model][1]


def lens_front(camera: str) -> float:
    return L.LENS_FRONT_X if camera == "ov2640" else picam_lens_front(camera)


def frustum(camera: str, length: float = 60.0) -> Part:
    """The camera's view, from its lens out to `length` past the muzzle."""
    front = lens_front(camera)
    return view_frustum(camera, (front, 0, 0), L.FLANGE_X[1] - front + length)


# -- the shared bulkhead body ------------------------------------------------------


def _bulkhead_base(fit: Fit) -> Part:
    """Flange, keyed slider and the screw's tail, open at the top and rear
    so a board drops in and its leads leave behind it."""
    t = L.BULKHEAD_WALL
    x0, x1 = L.BULKHEAD_X
    slider = BULKHEAD_SLIDE.slider(fit)
    ow = L.IN_HALF_W - fit.clearance
    oh = L.IN_HALF_H - fit.clearance
    hollow = box(x0 - 1, x1 - 0.01, -ow + t, ow - t, -oh + 2.0, oh + 1)
    fw, fh = L.FLANGE_SIZE
    flange = box(*L.FLANGE_X, -fw / 2, fw / 2, -fh / 2, fh / 2)
    # The tail: a floor plate back under the leads, and the nut's boss.
    tail = box(L.BULKHEAD_TAIL_X, x0 + 0.01, -8.0, 9.0, -oh, -oh + 2.0)
    boss = BULKHEAD_SCREW.boss(BULKHEAD_UP, size=7.0, height=5.0)
    body = (slider - hollow) + flange + tail + boss
    cuts = BULKHEAD_SCREW.nut_cuts(fit, BULKHEAD_UP) + BULKHEAD_SCREW.clear_hole(
        BULKHEAD_UP, depth=BULKHEAD_SCREW.clamp
    )
    return body - cuts


def _aperture(cameras: tuple[str, ...]) -> Part:
    """The flange's opening: every camera's view, so nothing of the case
    is ever in frame."""
    return union(frustum(c, 5.0) for c in cameras)


def _bulkhead_parts(fit: Fit, m: Module, name: str) -> None:
    if fit.fastener == "insert":
        m.add(
            bought(
                "m3-insert",
                BULKHEAD_SCREW.insert_location(),
                "insert, bulkhead screw",
                "bulkhead",
            )
        )
    else:
        m.add(
            bought(
                "m3-nut",
                BULKHEAD_SCREW.nut_location(fit, BULKHEAD_UP),
                "nut, bulkhead screw",
                "bulkhead",
            )
        )
    m.fit(name, m.bought[-1].label)
    m.add(
        bought(
            "m3x12",
            BULKHEAD_SCREW.screw_location(),
            "bulkhead screw",
            "bulkhead",
            teardown=True,
        )
    )


# -- the ESP32-CAM kit -------------------------------------------------------------


def esp32_location() -> Location:
    return Location((ESP32_BACK_X, 0, 0))


def _esp32_bulkhead(fit: Fit) -> Part:
    c = fit.clearance
    body = _bulkhead_base(fit)
    # Grooves in both side walls that the board's edges slide down into.
    # The board stands on the floor; the grooves are in the walls only.
    gy = ESP32_W / 2 + c
    floor = -L.IN_HALF_H + c + 2.0
    grooves = union(
        box(ESP32_BACK_X - c, ESP32_BACK_X + ESP32_PCB + c, y0, y1, floor, 30)
        for y0, y1 in ((gy - 1.0, gy + 0.8), (-gy - 0.8, -gy + 1.0))
    )
    # The camera: its body in a pocket behind the flange that sets the aim,
    # its lens through the flange, its cable out of the pocket's bottom.
    s = OV2640_BODY / 2 + c
    block = box(
        OV2640_BACK_X - 0.2, L.FLANGE_X[0] + 0.01, -s - 1.6, s + 1.6, -s - 1.6, s + 1.6
    )
    pocket = box(OV2640_BACK_X - 1, OV2640_BACK_X + OV2640_BODY_T + c, -s, s, -s, s)
    lens = cylinder((OV2640_BACK_X, 0, 0), X, OV2640_LENS_D / 2 + c, 20)
    fpc = box(OV2640_BACK_X - 1, OV2640_BACK_X + 0.8, -4.5, 4.5, -s - 3, -s + 0.01)
    # The capacitor's cradle on the tail.
    cx, cy, cz = CAPACITOR
    cradle = box(
        cx + 2, L.BULKHEAD_X[0] + 0.01, cy - 4.5, cy + 3.5, -L.IN_HALF_H + 2.2, cz
    )
    can = cylinder((cx, cy, cz), X, 4.0 + c, 13.5)
    body = body + block + cradle
    return body - union([grooves, pocket, lens, fpc, can, _aperture(("ov2640",))])


@cache
def esp32_kit(fit: Fit) -> Module:
    m = Module("esp32-cam")
    name = "bulkhead-esp32-cam"
    m.add(
        Printed(
            name, _esp32_bulkhead(fit), BULKHEAD_UP, "bulkhead", perimeters=3, infill=30
        )
    )
    _bulkhead_parts(fit, m, name)
    m.add(bought("esp32-cam", esp32_location(), "ESP32-CAM", "bulkhead"))
    m.add(bought("ov2640", Location((OV2640_BACK_X, 0, 0)), "camera", "bulkhead"))
    for pin in ESP32_PINS:
        px, py, pz = esp32_pin_position(pin)
        where = Location(
            Plane(origin=(ESP32_BACK_X + px, py, pz), x_dir=Z, z_dir=NEG_X)
        )
        m.add(bought("dupont1", where, f"lead on {pin}", "bulkhead"))
        m.fit(f"lead on {pin}", "ESP32-CAM")  # the housing goes over the pin
    m.add(bought("capacitor", Location(CAPACITOR), "capacitor", "bulkhead"))
    m.add(
        bought(
            "light-guide",
            Location((LIGHT_GUIDE[0], LIGHT_GUIDE[1], -14.0)),
            "light guide",
            "bulkhead",
        )
    )
    return m


# -- the Pi kit ----------------------------------------------------------------------


def _picam_bulkhead(fit: Fit) -> Part:
    body = _bulkhead_base(fit)
    pegs = union(p.peg(fit) for p in picam_pegs())
    # A clip over the camera board's top edge, its lip 1 mm over the back.
    top = PICAM_BOARD[3]
    arm = box(
        L.PICAM_PCB_BACK_X - 1.0,
        L.FLANGE_X[0] + 0.01,
        -3.0,
        3.0,
        top + fit.clearance,
        top + 2.0,
    )
    lip = box(
        L.PICAM_PCB_BACK_X - 1.0,
        L.PICAM_PCB_BACK_X - fit.clearance,
        -3.0,
        3.0,
        top - 1.0,
        top + 2.0,
    )
    # Room for either camera's lens housing in front of its board.
    housing = max(PICAM[m][0] for m in PICAM) / 2 + fit.clearance
    room = box(
        PICAM_PCB_FRONT_X, L.FLANGE_X[0] + 0.01, -housing, housing, -housing, housing
    )
    return body + pegs + arm + lip - room - _aperture(tuple(PICAM))


def picam_location() -> Location:
    return Location((L.PICAM_PCB_BACK_X, 0, 0))


def pi_location() -> Location:
    """The Pi frame in the gun: board x forward from the micro-SD end at
    PI_X0, board y up from the port edge at PI_Z0, components toward -y."""
    return Location(
        Plane(origin=(L.PI_X0, L.PI_PCB_Y, L.PI_Z0), x_dir=X, z_dir=(0, -1, 0))
    )


def _sled(fit: Fit) -> Part:
    c = fit.clearance
    y0, y1 = L.SLED_PLATE_Y
    plate = box(*L.SLED_X, y0, y1, *L.SLED_Z)
    # Notches for the left skin's screw boss (top, rear) and hook (front).
    notches = box(L.SLED_X[0] - 1, -78.0, y0 - 1, y1 + 1, 17.5, L.SLED_Z[1] + 1) + box(
        -25.5, -14.5, y0 - 1, y1 + 1, -5.5, 5.5
    )
    pegs = union(p.peg(fit) for p in pi_pegs())
    # Clips over the Pi's top edge clear of the header, and its back edge
    # above the micro-SD slot.
    top = L.PI_Z0 + 30.0
    face = L.PI_PCB_Y - 1.4
    clips = [
        box(-26.5, -24.0, face - 1.2, y0 + 0.01, top + c, top + 1.6),
        box(-26.5, -24.0, face - 1.2, face - c, top - 1.0, top + 1.6),
    ]
    back = L.PI_X0
    clips += [
        box(back - 1.6, back - c, face - 1.2, y0 + 0.01, 11.0, 16.0),
        box(back - 1.6, back + 1.0, face - 1.2, face - c, 11.0, 16.0),
    ]
    return plate - notches + pegs + union(clips)


@cache
def pi_kit(fit: Fit, camera: str) -> Module:
    m = Module("pi-zero-2w")
    name = "bulkhead-pi-camera"
    m.add(
        Printed(
            name, _picam_bulkhead(fit), BULKHEAD_UP, "bulkhead", perimeters=3, infill=30
        )
    )
    _bulkhead_parts(fit, m, name)
    m.add(
        Printed("sled-pi-zero-2w", _sled(fit), SLED_UP, "sled", perimeters=3, infill=30)
    )
    m.add(bought(f"picam-{camera}", picam_location(), "camera", "bulkhead"))
    m.add(bought("pi-zero-2w", pi_location(), "Pi Zero 2 W", "sled"))
    # The heatsink on the processor.
    sx, sy, _ = PI_SOC
    # On the envelope's top (it takes every part as 3.3 mm tall).
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
    # The LED and trigger lead: one 3-way housing on header pins 9, 11, 13.
    hx, hy = pi_header_pin(11)
    plastic = L.PI_PCB_Y - 1.4 - 2.5
    where = Location(
        Plane(origin=(L.PI_X0 + hx, plastic, L.PI_Z0 + hy), x_dir=X, z_dir=(0, -1, 0))
    )
    m.add(bought("dupont3", where, "lead on pins 9-11-13", "sled"))
    m.fit("lead on pins 9-11-13", "Pi Zero 2 W")
    # The USB cable's 90-degree plug in the data port, cable turned back.
    port = Location(
        Plane(
            origin=(L.PI_X0 + PI_USB_DATA_X, L.PI_PCB_Y - 1.4 - 1.3, L.PI_Z0 - 0.8),
            x_dir=X,
            z_dir=Z,
        )
    )
    m.add(bought("micro-usb-90", port, "USB plug", "sled"))
    m.fit("USB plug", "Pi Zero 2 W")
    return m


__all__ = ["esp32_kit", "pi_kit", "frustum", "Y", "teardrop"]
