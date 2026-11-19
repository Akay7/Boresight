"""The grip: a raked tube under the receiver's rear that takes a power drawer.

Printed standing on its base. From the bottom up: the drawer bay, keyed by
a rib down its front wall; the bay's ceiling, a 45-degree gable with a
10 mm flat where the drawer's contacts meet the battery lead's springs; a
small compartment for the wiring, flaring at 45 degrees into a bore up
through the grip's top; and the tenon that enters the receiver's floor,
with its through-bolt's crush bar. The top of its front is the trigger's
pocket. Down its back, a boss that the backstrap bolt crosses; at the
bottom of its front, a boss with the drawer thumbscrew's nut pocket.
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
from boresight_case.joints import (
    BACKSTRAP_BOLT,
    BAY_SLIDE,
    GRIP_BOLT,
    GRIP_JOINT,
    THUMBSCREW_FIX,
)
from boresight_case.model import Module, Printed, bought
from boresight_case.vendor import CONTACT_PLATE, M3_NUT_AF, M3_NUT_H

UP = tuple(-L.GRIP_D)  # printed standing on its base
D, F = L.GRIP_D, L.GRIP_F

CONTACT_A = (-7.5, 7.5)  # the two spring contacts on the ceiling flat
CHARGE_WINDOW = (105.0, 10.0)  # s, y of the 18650 charger's LED window, front wall
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
    """The tenon and its crush bar, its front face cut to the socket's
    45-degree slope."""
    t = GRIP_JOINT.tube(fit)
    inner = GRIP_JOINT.tenon_outer(fit)[1] / 2 - GRIP_JOINT.wall
    t = t + GRIP_BOLT.crush_tube(-inner - 0.01, inner + 0.01, UP)
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


def trigger_pocket(fit: Fit) -> Part:
    """The trigger housing's place in the top of the grip's front."""
    from boresight_case.parts.trigger import pocket_outline

    return pocket_outline(fit.clearance)


def _bosses() -> Part:
    """The boss down the back (the backstrap bolt's) and the boss at the
    bottom of the front (the thumbscrew nut's), each sloping at 45 degrees
    into the grip at its upper end so it prints without support."""
    half_w = L.GRIP_WIDTH / 2
    pieces = []
    for (s0, s1), (a0, a1), half in (
        (L.BACK_BOSS_S, L.BACK_BOSS_A, half_w),
        (L.FRONT_BOSS_S, L.FRONT_BOSS_A, L.FRONT_BOSS_Y),
    ):
        out = a1 - a0
        wall = a1 if a0 < -1 else a0  # the face it stands on
        sign = -1 if a0 < -1 else 1  # outward along a
        pts = [
            (wall, s1),
            (wall + sign * out, s1),
            (wall + sign * out, s0 + out),
            (wall, s0),
        ]
        # Drawn in the (a, s) plane through y = -half, extruded across +y.
        origin = L.grip_point(0, 0, -half)
        pieces.append(prism(origin, F, D, pts, 2 * half))
    return union(pieces)


def _thumbscrew_cuts(fit: Fit) -> Part:
    """The thumbscrew's hole up into the front boss, and a slot from the
    boss's front face that its nut drops into, flats across the axis."""
    c = fit.clearance
    seat = L.GRIP_LENGTH + L.DRAWER_FOOT - THUMBSCREW_FIX.clamp  # the nut's lower face
    hole = cylinder(L.grip_point(L.GRIP_LENGTH + 0.5, L.THUMB_A), tuple(-D), 1.7, 14.0)
    slot = grip_box(
        L.THUMB_A - M3_NUT_AF / 2 - c,
        L.FRONT_BOSS_A[1] + 1.0,
        -M3_NUT_AF / 2 - c,
        M3_NUT_AF / 2 + c,
        seat - M3_NUT_H - c,
        seat,
    )
    return hole + slot


def _charge_window() -> Part:
    """A hole in the front wall the 18650 charger's LEDs show through."""
    s, y = CHARGE_WINDOW
    return teardrop(
        L.grip_point(s, L.BAY_DEPTH / 2 - 0.5, y), tuple(F), 1.5, L.GRIP_WALL + 1.0, UP
    )


@cache
def grip(fit: Fit) -> Module:
    body = _outer() - _compartment() - (BAY_SLIDE.pocket() & bay_shape())
    body = body + _tenon(fit) + _bosses()
    cuts = [
        GRIP_BOLT.hole(-L.HALF_W, L.HALF_W, UP),
        BACKSTRAP_BOLT.hole(-L.GRIP_WIDTH / 2 - 1, L.GRIP_WIDTH / 2 + 1, UP),
        trigger_pocket(fit),
        _contact_tabs(),
        _charge_window(),
        _thumbscrew_cuts(fit),
    ]
    shape = body - union(cuts)
    m = Module("grip")
    m.add(Printed("grip", shape, UP, "grip", perimeters=4, infill=25))
    return m


def contacts(module: str = "battery lead") -> list:
    """The battery lead's two spring contacts, under the bay's ceiling:
    the drawer's flat contacts meet them as it is pushed home."""
    return [
        bought("spring-contact", where, f"spring contact {'+-'[i]}", module)
        for i, where in enumerate(contact_locations())
    ]


def thumbscrew_nut(fit: Fit, module: str = "drawer lock"):
    """The thumbscrew's nut, dropped into its slot in the front boss."""
    return bought(
        "m3-nut", THUMBSCREW_FIX.nut_location(fit, UP), "nut, thumbscrew", module
    )
