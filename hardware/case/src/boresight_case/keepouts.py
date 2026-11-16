"""The skin interface's zones: where no skin may go, and the core it covers.

Each zone is the union over every valid configuration, so one set of skins
fits every board kit, drawer and switch plate. Zones extend well outside
the core: a skin that reaches into one anywhere is refused.
"""

from __future__ import annotations

from functools import cache

from build123d import Part

from boresight_case import layout as L
from boresight_case.config import MECHANISMS, TRIGGERS
from boresight_case.geom import X, box, oriented_box, side_profile, union, unit, v
from boresight_case.interfaces import Fit
from boresight_case.joints import BULKHEAD_SCREW, CASSETTE_SCREW, MODULE_JOINTS
from boresight_case.parts import kits
from boresight_case.parts.grip import CHARGE_WINDOW, grip_box
from boresight_case.parts.rear_cap import LED_AT, ROCKER_AT
from boresight_case.parts.trigger import STOP_Z, lever_sweep
from boresight_case.vendor import ROCKER_BEZEL

REACH = 60.0  # how far zones run out past the core


def square(start, axis, side: float, length: float) -> Part:
    """A square prism from `start` along `axis`. Zones that cross a skin
    sideways are square, not round, so the hole they leave in a skin printed
    flank-down has a short flat bridge for a roof, not an overhang."""
    a = unit(axis)
    other = v((0, 1, 0) if abs(a.Y) < 0.9 else (1, 0, 0))
    p1 = (other - a * other.dot(a)).normalized()
    p2 = a.cross(p1)
    return oriented_box(v(start) + a * (length / 2), p1, p2, (side, side, length))


def _view() -> dict[str, Part]:
    return {f"view {cam}": kits.frustum(cam, REACH) for cam in ("ov2640", "cm2", "cm3")}


def _vents() -> Part:
    x0, x1 = L.SOC_VENT_X
    # Outside the receiver's right wall and top, over every slot.
    side = box(x0 - 0.5, x1 + 0.5, -L.HALF_W - REACH, -L.HALF_W, -5.5, 15.5)
    top = box(x0 - 0.5, x1 + 0.5, -9.5, 5.5, L.HALF_H, L.HALF_H + REACH)
    return side + top


@cache
def trigger_zone(mechanism: str) -> Part:
    """One mechanism's trigger zone: its travel with either plate, the
    finger's room in front of it, the stop screw's access and the hex key's
    way up to the cassette screw from below the cassette (the way through
    the cassette itself is the core's own business)."""
    screw = square((*CASSETTE_SCREW.entry[:2], L.CASSETTE_Z[0]), (0, 0, -1), 6.0, REACH)
    if mechanism == "button":
        from boresight_case.parts import button as B

        sweep = union(B.button_sweep(t) for t in TRIGGERS)
        # A millimetre round the cap all along its travel, so no skin
        # touches it; the finger in front, and the hex key through the cap
        # to the stop screw.
        travel = max(L.STOP_TRAVEL.values())
        margin = box(
            B.CAP_X[0] - travel - 1.0,
            B.CAP_X[1] + 1.0,
            B.CAP_Y[0] - 1.0,
            B.CAP_Y[1] + 1.0,
            B.CAP_Z[0] - 1.0,
            B.CAP_Z[1] + 1.0,
        )
        finger = box(B.CAP_X[1], B.CAP_X[1] + 14.0, -10.0, 10.0, -62.0, -36.0)
        return sweep + margin + finger + screw
    sweep = union(lever_sweep(t, mechanism=mechanism) for t in TRIGGERS)
    finger = box(L.PIVOT.X - 2.0, -2.0, -10.0, 10.0, -84.0, L.CASSETTE_Z[0])
    stop = square((L.FRONT_WALL_X[1], 0, STOP_Z), X, 9.0, 25.0)
    return sweep + finger + stop + screw


def _trigger() -> Part:
    """Every mechanism's trigger zone: one set of skins fits them all."""
    return union(trigger_zone(m) for m in MECHANISMS)


def _drawer() -> Part:
    """Everything below the grip's base: the drawer slides out, its latch
    is pressed, the 18650's port is plugged and the tether's cable leaves."""
    return grip_box(
        -L.GRIP_DEPTH / 2 - 1.0,
        L.GRIP_DEPTH / 2 + 1.0,
        -L.GRIP_WIDTH / 2 - 1.0,
        L.GRIP_WIDTH / 2 + 1.0,
        L.GRIP_LENGTH,
        L.GRIP_LENGTH + REACH,
    )


def _charge_indicator() -> Part:
    s, y = CHARGE_WINDOW
    return square(L.grip_point(s, L.GRIP_DEPTH / 2, y), tuple(L.GRIP_F), 6.0, REACH)


def _power_switch() -> Part:
    y, z = ROCKER_AT
    bx, by, _ = ROCKER_BEZEL
    return box(
        L.REAR_CAP_PLATE[0] - REACH,
        L.REAR_CAP_PLATE[0],
        y - bx / 2 - 3,
        y + bx / 2 + 3,
        z - by / 2 - 3,
        z + by / 2 + 3,
    )


def _status_leds() -> Part:
    guide = square(
        (kits.LIGHT_GUIDE[0], kits.LIGHT_GUIDE[1], L.HALF_H), (0, 0, 1), 6.0, REACH
    )
    rear = square((L.REAR_CAP_PLATE[0], LED_AT[1], LED_AT[2]), (-1, 0, 0), 7.0, REACH)
    return guide + rear


def _screw_access() -> Part:
    """The heads of the screws a teardown undoes from outside the core."""
    heads = [j.head_clearance() for j in MODULE_JOINTS]
    heads.append(square(BULKHEAD_SCREW.entry, (0, 0, -1), 8.0, REACH))
    return union(heads)


def _removal() -> Part:
    """The rear cap slides out backward, the bulkhead forward."""
    rear = box(
        L.REAR_CAP_PLATE[0] - REACH,
        L.RECEIVER_X[0],
        -L.HALF_W - 0.5,
        L.HALF_W + 0.5,
        -L.HALF_H - 0.5,
        L.HALF_H + 0.5,
    )
    fw, fh = L.FLANGE_SIZE
    front = box(
        L.BARREL_X[1],
        L.FLANGE_X[1] + REACH,
        -fw / 2 - 0.5,
        fw / 2 + 0.5,
        -fh / 2 - 0.5,
        fh / 2 + 0.5,
    )
    return rear + front


@cache
def zones() -> dict[str, Part]:
    """Every keep-out zone, by name."""
    z = _view()
    z.update(
        {
            "vents": _vents(),
            "trigger": _trigger(),
            "drawer and latch": _drawer(),
            "charge indicator": _charge_indicator(),
            "power switch": _power_switch(),
            "status LEDs": _status_leds(),
            "screw access": _screw_access(),
            "rear cap and bulkhead removal": _removal(),
        }
    )
    return z


def hook_room() -> Part:
    """The space each skin hook takes through and behind the core's wall:
    the one place a skin enters the core."""
    from boresight_case.joints import ATTACHMENTS

    fit = Fit()
    return union(a.slot(fit, (0, 0, 1)) for a in ATTACHMENTS.values()) + union(
        a.hook_tab() for a in ATTACHMENTS.values()
    )


@cache
def core_envelope() -> Part:
    """The core's outside, filled: the body (rear cap to muzzle), the
    bulkhead's flange, the trigger cassette and its rails, and the grip,
    less the room the skins' hooks take."""
    hw, hh = L.HALF_W, L.HALF_H
    fw, fh = L.FLANGE_SIZE
    cw = L.CASSETTE_HALF_W
    parts = [
        box(L.REAR_CAP_PLATE[0], L.BARREL_X[1], -hw, hw, -hh, hh),
        box(*L.FLANGE_X, -fw / 2, fw / 2, -fh / 2, fh / 2),
        box(*L.CASSETTE_X, -cw, cw, L.CASSETTE_Z[0], L.FLOOR_Z),
        box(*L.CASSETTE_X, -13.25, 13.25, L.FLOOR_Z - 2.0, L.FLOOR_Z),
        side_profile(
            L.grip_outline(0.0, L.GRIP_LENGTH), -L.GRIP_WIDTH / 2, L.GRIP_WIDTH / 2
        )
        & box(-300, 0, -50, 50, -300, L.FLOOR_Z),
    ]
    return union(parts) - hook_room()
