"""The skin interface's zones: where no cover may go, and the core it covers.

The covers are the same parts in every configuration, so each section's
zones are the union over every valid configuration, in that section's own
place: the receiver's and the grip's where they are, a barrel's as the
first barrel's, the muzzle ring's at a muzzle of x = 100. `zones(cfg)`
places them on a whole gun. Zones extend well outside the core: a cover
that reaches into one anywhere is refused.

The antenna zones keep out metal only: a plastic cover may pass through
them, a metal or metal-filled one may not.
"""

from __future__ import annotations

from functools import cache

from build123d import Location, Part

from boresight_case import layout as L
from boresight_case.config import MECHANISMS, TRIGGERS, Config
from boresight_case.geom import X, box, oriented_box, union, unit, v
from boresight_case.interfaces import FLANGE
from boresight_case.joints import (
    BACKSTRAP_BOLT,
    GRIP_BOLT,
    THUMBSCREW_FIX,
    TRIGGER_BOLT,
    ports,
)
from boresight_case.parts import kits
from boresight_case.parts.grip import CHARGE_WINDOW, grip_box
from boresight_case.vendor import ESP32_ANTENNA, PI_ANTENNA, SLIDE_LEVER, SLIDE_THROW

REACH = 60.0  # how far zones run out past the core
MUZZLE = kits.MUZZLE


def square(start, axis, side: float, length: float) -> Part:
    """A square prism from `start` along `axis`. Zones that cross a cover
    sideways are square, not round, so the hole they leave in a cover
    printed flank-down has a short flat bridge for a roof."""
    a = unit(axis)
    other = v((0, 1, 0) if abs(a.Y) < 0.9 else (1, 0, 0))
    p1 = (other - a * other.dot(a)).normalized()
    p2 = a.cross(p1)
    return oriented_box(v(start) + a * (length / 2), p1, p2, (side, side, length))


def outside_left(x: float, z: float, side: float) -> Part:
    return square((x, L.HALF_W, z), (0, 1, 0), side, REACH)


# -- the receiver's -------------------------------------------------------------------


@cache
def trigger_zone(mechanism: str) -> Part:
    """One mechanism's trigger zone: its travel with either plate, the
    finger's room in front of it, the stop screw's and the mounting bolt's
    access from below."""
    from boresight_case.parts import trigger as T

    if mechanism == "button":
        from boresight_case.parts import button as B

        sweep = union(B.button_sweep(t) for t in TRIGGERS)
        finger_x = B.FRONT_X
    else:
        sweep = union(T.lever_sweep(t) for t in TRIGGERS)
        finger_x = T.CONTACT_X
    finger = box(
        finger_x - 1.0,
        L.FRONT_BLOCK_X[0] - 0.5,
        -10.0,
        10.0,
        L.TRIGGER_Z[0] - 20.0,
        T.P.Z - 7.5,
    )
    stop = square((L.STOP_X, L.STOP_Y, L.FRONT_BLOCK_BOTTOM), (0, 0, -1), 8.0, REACH)
    e = TRIGGER_BOLT.entry
    key = square((e[0], e[1], L.TRIGGER_Z[0]), (0, 0, -1), 7.0, REACH)
    return sweep + finger + stop + key


def _trigger() -> Part:
    return union(trigger_zone(m) for m in MECHANISMS)


def _switch_and_lights() -> Part:
    """The power switch's knob and its throw, the two LEDs, and the Start
    and Select buttons, out through the left wall."""
    kx, ky, _ = SLIDE_LEVER
    x, z = L.SWITCH_AT
    switch = box(
        x - (kx + SLIDE_THROW) / 2 - 3,
        x + (kx + SLIDE_THROW) / 2 + 3,
        L.HALF_W,
        L.HALF_W + REACH,
        z - ky / 2 - 3,
        z + ky / 2 + 3,
    )
    leds = union(
        outside_left(lx, lz, 6.0) for lx, lz in (L.POWER_LED_AT, L.STATUS_LED_AT)
    )
    buttons = union(outside_left(bx, bz, 8.0) for bx, bz in L.BUTTON_AT)
    return switch + leds + buttons


def _rear_cap_removal() -> Part:
    return box(
        L.REAR_CAP_PLATE[0] - REACH,
        L.RECEIVER_X[0],
        -L.HALF_W,
        L.HALF_W,
        -L.HALF_H,
        L.HALF_H,
    )


# -- the grip's ---------------------------------------------------------------------


def _drawer() -> Part:
    """Everything below the grip's base: the drawer and its foot slide out,
    the thumbscrew turns, the 18650's port is plugged and the tether's
    cable leaves."""
    return grip_box(
        -L.GRIP_DEPTH / 2 - 1.0,
        L.FRONT_BOSS_A[1] + 1.0,
        -L.GRIP_WIDTH / 2 - 1.0,
        L.GRIP_WIDTH / 2 + 1.0,
        L.GRIP_LENGTH,
        L.GRIP_LENGTH + REACH,
    )


def _charge_indicator() -> Part:
    s, y = CHARGE_WINDOW
    return square(L.grip_point(s, L.GRIP_DEPTH / 2, y), tuple(L.GRIP_F), 6.0, REACH)


def _thumbscrew() -> Part:
    """The thumbscrew's head, under the front boss."""
    e = THUMBSCREW_FIX.entry
    return square(e, tuple(L.GRIP_D), 13.0, REACH)


# -- a barrel's (the first barrel's place) ---------------------------------------------


def _window() -> Part:
    """Under the window: the plugs, their cables and the clamp bar."""
    x0, x1 = L.WINDOW_X
    return box(
        x0 - 1.0,
        kits.CLAMP_X[1] + 3.0,
        -L.HALF_W - 1.0,
        L.HALF_W + 1.0,
        L.FLOOR_Z - REACH,
        L.FLOOR_Z,
    )


def _vents() -> Part:
    """Outside the right wall's window over the Pi's processor."""
    from boresight_case.parts.barrel import SIDE_WINDOW_X, SIDE_WINDOW_Z

    x0, x1 = SIDE_WINDOW_X
    z0, z1 = SIDE_WINDOW_Z
    return box(x0, x1, -L.HALF_W - REACH, -L.HALF_W, z0, z1 + 8.0)


# -- the muzzle ring's (a muzzle at x = 100) -------------------------------------------


def _views() -> dict[str, Part]:
    return {f"view {cam}": kits.frustum(cam, REACH) for cam in ("ov2640", "cm2", "cm3")}


def _nose_top() -> Part:
    """The debug socket, the BOOT button and the light guide on the nose's
    top."""
    sx0, sx1 = kits.SOCKET_X
    socket = box(
        sx0 - 3.0,
        sx1 + 3.0,
        kits.SOCKET_Y - 6.0,
        kits.SOCKET_Y + 6.0,
        L.HALF_H,
        L.HALF_H + REACH,
    )
    bx, by = kits.BOOT_AT
    boot = square((bx, by, L.HALF_H), (0, 0, 1), 10.0, REACH)
    gx, gy, _ = kits.led_point()
    guide = square((gx, gy, L.HALF_H), (0, 0, 1), 6.0, REACH)
    return socket + boot + guide


def _module_removal() -> Part:
    """The camera module and the nose come out forward."""
    from build123d import Plane as P_
    from build123d import Rectangle, loft

    g = 0.3  # the ring keeps this far off the nose, past a 45-degree lead-in
    near = P_(origin=(MUZZLE - g, 0, 0), z_dir=(1, 0, 0)) * Rectangle(
        2 * L.HALF_H, 2 * L.HALF_W
    )
    far = P_(origin=(MUZZLE, 0, 0), z_dir=(1, 0, 0)) * Rectangle(
        2 * (L.HALF_H + g), 2 * (L.HALF_W + g)
    )
    lead_in = loft([near, far])
    return lead_in + box(
        MUZZLE - 0.01,
        MUZZLE + REACH,
        -L.HALF_W - g,
        L.HALF_W + g,
        -L.HALF_H - g,
        L.HALF_H + g,
    )


# -- bolts ------------------------------------------------------------------------


def _bolt_access(barrels: int) -> Part:
    """Each through-bolt's head and hex key on the left, its nut's room on
    the right, outside the covers."""
    from boresight_case.joints import through_bolts

    return union(b.head_room(REACH) + b.nut_room(REACH) for b in through_bolts(barrels))


# -- the antennas (metal only) ---------------------------------------------------------


def antenna_zones() -> dict[str, Part]:
    """10 mm round each board's PCB antenna, in its kit's place (a muzzle
    at x = 100): no metal may enter."""
    from boresight_case.geom import cylinder  # noqa: F401  (kept for remixes)

    x0, x1, y0, y1, z0, z1 = ESP32_ANTENNA
    esp = kits.esp32_location() * box(
        x0 - 10, x1 + 10, y0 - 10, y1 + 10, z0 - 10, z1 + 10
    )
    px0, px1, py0, py1, pz0, pz1 = PI_ANTENNA
    pi = kits.pi_location() * box(
        px0 - 10, px1 + 10, py0 - 10, py1 + 10, pz0 - 10, pz1 + 10
    )
    return {"antenna esp32-cam": esp, "antenna pi-zero-2w": pi}


def antenna_solids() -> dict[str, Part]:
    """The antennas themselves, in their kits' place."""
    x0, x1, y0, y1, z0, z1 = ESP32_ANTENNA
    px0, px1, py0, py1, pz0, pz1 = PI_ANTENNA
    return {
        "esp32-cam": kits.esp32_location() * box(x0, x1, y0, y1, z0, z1),
        "pi-zero-2w": kits.pi_location() * box(px0, px1, py0, py1, pz0, pz1),
    }


# -- placing them ---------------------------------------------------------------------


@cache
def section_zones() -> dict[str, dict[str, Part]]:
    """Every zone, by the section whose place it is drawn in: 'gun' (the
    receiver's and the grip's, which do not move), 'barrel' (the first
    barrel's place) and 'muzzle' (a muzzle at x = 100)."""
    gun = {
        "trigger": _trigger(),
        "switch, LEDs and buttons": _switch_and_lights(),
        "rear cap removal": _rear_cap_removal(),
        "drawer and thumbscrew": _drawer() + _thumbscrew(),
        "charge indicator": _charge_indicator(),
    }
    barrel = {"window and plugs": _window(), "vents": _vents()}
    muzzle = dict(_views())
    muzzle["nose top"] = _nose_top()
    muzzle["camera and nose removal"] = _module_removal()
    return {"gun": gun, "barrel": barrel, "muzzle": muzzle}


def _move(shape: Part, dx: float) -> Part:
    return Location((dx, 0, 0)) * shape if dx else shape


@cache
def zones(cfg: Config | None = None) -> dict[str, Part]:
    """Every keep-out zone placed on a gun of `cfg`'s barrel count (one
    barrel when none is given), by name."""
    barrels = 1 if cfg is None else cfg.barrels
    s = section_zones()
    out = dict(s["gun"])
    for name, z in s["barrel"].items():
        if barrels:
            out[name] = union(_move(z, k * L.BARREL_LEN) for k in range(barrels))
    dx = L.muzzle_x(barrels) - MUZZLE
    for name, z in s["muzzle"].items():
        out[name] = _move(z, dx)
    out["bolt access"] = _bolt_access(barrels)
    return out


@cache
def metal_zones(cfg: Config | None = None) -> dict[str, Part]:
    barrels = 1 if cfg is None else cfg.barrels
    dx = L.muzzle_x(barrels) - MUZZLE
    return {n: _move(z, dx) for n, z in antenna_zones().items()}


def _trigger_envelope(housing: Part) -> Part:
    """The trigger housing grown by half a millimetre front, back and below:
    covers keep off it all round."""
    return (
        housing
        + Location((0.5, 0, 0)) * housing
        + Location((-0.5, 0, 0)) * housing
        + Location((0, 0, -0.5)) * housing
    )


@cache
def core_envelope(cfg: Config | None = None) -> Part:
    """The core's outside, filled: the body from the rear cap to the muzzle,
    the camera module's plate or the nose, the trigger housing and the
    grip with its bosses and the drawer's foot."""
    from boresight_case.geom import side_profile
    from boresight_case.parts.trigger import outline

    barrels = 1 if cfg is None else cfg.barrels
    hw, hh = L.HALF_W, L.HALF_H
    m = L.muzzle_x(barrels)
    gw = L.GRIP_WIDTH / 2
    below = box(-300, 0, -50, 50, -300, L.FLOOR_Z)
    grip = side_profile(L.grip_outline(0.0, L.GRIP_LENGTH), -gw, gw) & below
    bosses = grip_box(*L.BACK_BOSS_A, -gw, gw, *L.BACK_BOSS_S) + grip_box(
        *L.FRONT_BOSS_A, -L.FRONT_BOSS_Y, L.FRONT_BOSS_Y, *L.FRONT_BOSS_S
    )
    foot = grip_box(
        -L.BAY_DEPTH / 2,
        L.FRONT_BOSS_A[1],
        -gw,
        gw,
        L.GRIP_LENGTH,
        L.GRIP_LENGTH + L.DRAWER_FOOT,
    )
    from boresight_case.parts.button import _stop_boss

    t = L.TRIGGER_HALF_W + 0.5  # covers keep half a millimetre off the trigger
    stop = _stop_boss().bounding_box()
    parts = [
        box(L.REAR_CAP_PLATE[0], m + L.NOSE_LEN, -hw, hw, -hh, hh),
        _trigger_envelope(side_profile(outline(), -t, t)),
        box(
            stop.min.X - 0.5,
            stop.max.X + 0.5,
            -t,
            t,
            stop.min.Z - 0.5,
            stop.max.Z + 0.5,
        ),
        grip,
        bosses,
        foot,
    ]
    return union(parts)


__all__ = [
    "zones",
    "metal_zones",
    "core_envelope",
    "trigger_zone",
    "section_zones",
    "antenna_solids",
    "FLANGE",
    "X",
    "BACKSTRAP_BOLT",
    "GRIP_BOLT",
    "ports",
]
