"""The grip: a raked tube under the receiver's rear that takes a power drawer.

Printed standing on its base. From the bottom up: the drawer bay, keyed by
a rib down its front wall; the bay's ceiling, a 45-degree gable with a
10 mm flat carrying the two spring contacts the drawer presses on; a
small compartment for the wiring, flaring at 45 degrees into a bore up
through the grip's top; and the tenon that enters the receiver's floor.
The power switch and regulator are in the rear cap.
"""

from __future__ import annotations

from functools import cache

from build123d import Location, Part, Plane, Rectangle, loft

from boresight_case import layout as L
from boresight_case.geom import (
    Y,
    box,
    cylinder,
    oriented_box,
    prism,
    side_profile,
    teardrop,
    union,
)
from boresight_case.interfaces import Fit
from boresight_case.joints import ATTACHMENTS, BAY_SLIDE, GRIP_JOINT
from boresight_case.model import Module, Printed, bought
from boresight_case.vendor import CONTACT_PLATE

UP = tuple(-L.GRIP_D)  # printed standing on its base
D, F = L.GRIP_D, L.GRIP_F

CONTACT_A = (-7.5, 7.5)  # the two spring contacts on the ceiling flat
CABLE_HOLE = (14.0, 8.0)  # a, y of the hole for the Pi's USB cable through the ceiling
# The drawer latch's notch, in the front wall's inside just above the base:
# s range, y range.
LATCH_NOTCH = ((112.75, 115.5), (4.5, 9.5))
CHARGE_WINDOW = (105.0, 7.0)  # s, y of the 18650 charger's LED window, front wall
COMPARTMENT_FLOOR = L.BAY_CEILING_S - L.CEILING_T


def grip_box(a0: float, a1: float, y0: float, y1: float, s0: float, s1: float) -> Part:
    """A box in the grip's frame: a toward the front, y across, s down."""
    centre = L.grip_point((s0 + s1) / 2, (a0 + a1) / 2, (y0 + y1) / 2)
    # oriented_box's third axis is F x Y, which is -D.
    return oriented_box(centre, F, Y, (a1 - a0, y1 - y0, s1 - s0))


def _gable(
    a_half: float, half_flat: float, half_width: float, s_flat: float, s_end: float
) -> Part:
    """The bay's cross-section with its gable top, extruded along a: the flat
    is `half_flat` each side of the middle at `s_flat`, widening at 45
    degrees to `half_width`, then straight down to `s_end`."""
    rise = half_width - half_flat
    pts = [
        (-half_flat, s_flat),
        (half_flat, s_flat),
        (half_width, s_flat + rise),
        (half_width, s_end),
        (-half_width, s_end),
        (-half_width, s_flat + rise),
    ]
    # Drawn in the plane through the grip axis spanned by y and the axis (s
    # as -D so the polygon's s grows downward), extruded along a both ways.
    origin = L.grip_point(0)
    return prism(origin + F * a_half, Y, D, pts, 2 * a_half)


def bay_shape(c: float = 0.0) -> Part:
    """The bay, or (with c > 0) the drawer's outline inside it: the keyed
    slide, under the gable, inset by c on every side."""
    gable = _gable(
        L.BAY_DEPTH / 2 - c,
        L.CEILING_FLAT / 2
        - c * 0.4142,  # a 45-degree face moves c sideways by c tan 22.5
        L.BAY_WIDTH / 2 - c,
        L.BAY_CEILING_S + c,
        L.GRIP_LENGTH + 5,
    )
    return gable


def _outer() -> Part:
    body = grip_box(
        -L.GRIP_DEPTH / 2,
        L.GRIP_DEPTH / 2,
        -L.GRIP_WIDTH / 2,
        L.GRIP_WIDTH / 2,
        L.GRIP_TOP_S,
        L.GRIP_LENGTH,
    )
    # A hair under the receiver's underside: the faces meet, but a large
    # tilted contact would otherwise tessellate into overlap noise.
    below = box(-200, 50, -50, 50, -300, L.FLOOR_Z - 0.05)
    return body & below


FUNNEL_S = (10.0, 16.0)  # the compartment narrows from s=16 up to s=10
BORE_BOTTOM_Z = -37.0


def _compartment() -> Part:
    """The space above the ceiling: full width from the ceiling up to
    FUNNEL_S[1], narrowing at 45 degrees (in the print's frame) to
    FUNNEL_S[0], and a bore straight up from there to the tenon's mouth."""
    half_a, half_y = L.BAY_DEPTH / 2, L.BAY_WIDTH / 2
    s_top, s_full = FUNNEL_S
    main = grip_box(-half_a, half_a, -half_y, half_y, s_full - 0.01, COMPARTMENT_FLOOR)
    step = s_full - s_top
    low = Plane(origin=L.grip_point(s_full), x_dir=F, z_dir=-D) * Rectangle(
        2 * half_a, 2 * half_y
    )
    high = Plane(origin=L.grip_point(s_top), x_dir=F, z_dir=-D) * Rectangle(
        2 * (half_a - step), 2 * (half_y - step)
    )
    tenon_w, tenon_y = GRIP_JOINT.tenon_outer(Fit())
    bw, by = tenon_w - 2 * GRIP_JOINT.wall, tenon_y - 2 * GRIP_JOINT.wall
    bore = box(
        L.GRIP_TOP.X - bw / 2,
        L.GRIP_TOP.X + bw / 2,
        -by / 2,
        by / 2,
        BORE_BOTTOM_Z,
        L.FLOOR_Z + 0.01,
    )
    return main + loft([low, high]) + bore


def _tenon(fit: Fit) -> Part:
    """The tenon, its front face cut to the socket's 45-degree slope."""
    t = GRIP_JOINT.tenon(fit, UP)
    x_front = L.GRIP_TOP.X + L.GRIP_JOINT[0] / 2  # the socket's front at the floor
    off = fit.clearance * 2**0.5
    z0, z1 = L.FLOOR_Z - 6, L.FLOOR_Z + L.GRIP_JOINT_DEPTH + 2
    slope = side_profile(
        [
            (x_front - off + 6, z0),
            (x_front + 20, z0),
            (x_front + 20, z1),
            (x_front - off - (z1 - L.FLOOR_Z), z1),
        ],
        -30,
        30,
    )
    return t - slope


def contact_locations() -> list[Location]:
    """The spring contacts: plates under the ceiling flat, springs toward
    the drawer."""
    return [
        Location(
            Plane(origin=L.grip_point(L.BAY_CEILING_S + 0.5, a, 0), x_dir=F, z_dir=-D)
        )
        for a in CONTACT_A
    ]


def _contact_tabs() -> Part:
    """Slots through the ceiling for the contacts' solder tabs."""
    sx = CONTACT_PLATE[0]
    return union(
        grip_box(
            a + sx / 2 - 2.0,
            a + sx / 2 - 0.5,
            -1.5,
            1.5,
            COMPARTMENT_FLOOR - 1,
            L.BAY_CEILING_S + 1,
        )
        for a in CONTACT_A
    )


def _latch_notch() -> Part:
    (s0, s1), (y0, y1) = LATCH_NOTCH
    front = L.BAY_DEPTH / 2
    return grip_box(front - 0.1, front + 1.15, y0, y1, s0, s1)


def _charge_window() -> Part:
    """A hole in the front wall the 18650 charger's LEDs show through."""
    s, y = CHARGE_WINDOW
    return teardrop(
        L.grip_point(s, L.BAY_DEPTH / 2 - 0.5, y), tuple(F), 1.5, L.GRIP_WALL + 1.0, UP
    )


@cache
def grip(fit: Fit) -> Module:
    bosses = union(ATTACHMENTS[("grip", s)].core_boss(UP) for s in ("left", "right"))
    body = _outer() - _compartment() - (BAY_SLIDE.pocket() & bay_shape())
    body = body + _tenon(fit) + bosses
    cuts = [
        GRIP_JOINT.tenon_cuts(fit, UP),
        cylinder(L.grip_point(COMPARTMENT_FLOOR - 1, *CABLE_HOLE), tuple(D), 3.0, 10.0),
        _contact_tabs(),
        _latch_notch(),
        _charge_window(),
    ]
    cuts += [ATTACHMENTS[("grip", s)].core_cuts(fit, UP) for s in ("left", "right")]
    shape = body - union(cuts)

    m = Module("grip")
    m.add(Printed("grip", shape, UP, "grip", perimeters=4, infill=25))
    if fit.fastener == "insert":
        m.add(
            bought(
                "m3-insert",
                GRIP_JOINT.insert_location(fit),
                "insert, grip joint",
                "grip",
            )
        )
    else:
        m.add(
            bought(
                "m3-nut", GRIP_JOINT.nut_location(fit, UP), "nut, grip joint", "grip"
            )
        )
    m.fit("grip", m.bought[-1].label)
    for side in ("left", "right"):
        a = ATTACHMENTS[("grip", side)]
        if fit.fastener == "insert":
            m.add(
                bought(
                    "m3-insert",
                    a.insert_location(),
                    f"insert, grip skin {side}",
                    "grip",
                )
            )
        else:
            m.add(
                bought("m3-nut", a.nut_location(UP), f"nut, grip skin {side}", "grip")
            )
        m.fit("grip", m.bought[-1].label)
    return m


def contacts(module: str = "grip") -> list:
    """The two spring contacts a battery or ESP32-CAM tether build fits
    under the bay's ceiling."""
    return [
        bought("spring-contact", where, f"spring contact {'+-'[i]}", module)
        for i, where in enumerate(contact_locations())
    ]
