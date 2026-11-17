"""The power drawers: one per kind, all the same outside.

A drawer is a frame that slides up into the grip's bay: a top block whose
two flat contacts meet the spring contacts under the bay's ceiling as it
latches, a spine down its back, and a base that closes the grip's bottom.
A groove down its front fits the bay's key rib, so it goes in only one way
round. A tongue in the base's front edge hooks into a notch in the grip's
front wall; press it back, from below, to release the drawer.

Each kind adds what it holds: a cell holder between the base and a stop
plate, the 18650's charger with its port through the base, or the tether's
cable weaving through three posts and out of the base.

Drawers print standing on their spine.
"""

from __future__ import annotations

from functools import cache

from build123d import Location, Part, Plane

from boresight_case import layout as L
from boresight_case.geom import Y, union
from boresight_case.interfaces import Fit
from boresight_case.joints import BAY_SLIDE
from boresight_case.model import PETG, Module, Printed, bought
from boresight_case.parts.grip import CONTACT_A, LATCH_NOTCH, bay_shape, grip_box
from boresight_case.vendor import CONTACT_PLATE, HOLDERS, TP4056, TP4056_PORT

D, F = L.GRIP_D, L.GRIP_F
UP = tuple(F)  # printed on the spine, front up

# The top face, where the springs' tips press: the ceiling, the spring
# contact's plate, and the spring compressed.
TOP_S = L.BAY_CEILING_S + 0.5 + 3.5
TOP_T = 2.5
BASE_S = L.GRIP_LENGTH - 5.0  # the base's inner face
SPINE_A = -L.BAY_DEPTH / 2 + 2.75  # the spine's front face
HOLDER_A0 = SPINE_A  # holders sit against the spine
TONGUE_A = 15.5  # the latch tongue's back face
HOOK = 0.9  # how far the hook stands proud of the drawer's front
CABLE_Y = 8.0  # the tether's cable, across y
CABLE_A = 11.0  # and along a, in front of the top block
TP4056_A = 8.0  # the charger's PCB back face
TP4056_S = BASE_S + 1.0 - TP4056[0] - 1.0  # the charger's far end


def outline(fit: Fit) -> Part:
    """The drawer's outside: the keyed slide under the bay's gable, inset by
    the clearance, from its top face to the grip's base."""
    c = fit.clearance
    span = grip_box(-30, 30, -30, 30, TOP_S, L.GRIP_LENGTH)
    return bay_shape(c) & BAY_SLIDE.slider(fit) & span


def _band(fit: Fit, s0: float, s1: float, a0: float = -30, a1: float = 30) -> Part:
    return outline(fit) & grip_box(a0, a1, -30, 30, s0, s1)


def _frame(fit: Fit, top_a1: float = 30.0) -> Part:
    """Spine, top block (to `top_a1` along a) and base, with the contact
    plates' pockets and the latch tongue."""
    spine = _band(fit, TOP_S, L.GRIP_LENGTH, -30, SPINE_A)
    top = _band(fit, TOP_S, TOP_S + TOP_T, -30, top_a1)
    base = _band(fit, BASE_S, L.GRIP_LENGTH)
    frame = spine + top + base
    sx = CONTACT_PLATE[0] / 2 + 0.2
    pockets = union(
        grip_box(a - sx, a + sx, -sx, sx, TOP_S - 0.1, TOP_S + CONTACT_PLATE[2])
        for a in CONTACT_A
    )
    # The contact tabs pass through to the wiring inside.
    tabs = union(
        grip_box(a + 2.0, a + 3.5, -1.5, 1.5, TOP_S - 0.1, TOP_S + TOP_T + 0.1)
        for a in CONTACT_A
    )
    return frame - pockets - tabs + _latch(fit) - _latch_cuts(fit)


def _latch(fit: Fit) -> Part:
    """The tongue's hook: on its front face, a 45-degree lead-in on top so
    the drawer pushes past the bay's front wall."""
    front = L.BAY_DEPTH / 2 - fit.clearance
    (s0, s1), (y0, y1) = LATCH_NOTCH
    hook_s = (s0 + 0.5, s0 + 0.5 + HOOK + 1.2)
    ys = (y0 + 0.5, y1 - 0.5)
    pts = [
        (front - 0.01, hook_s[1]),
        (front + HOOK, hook_s[1]),
        (front + HOOK, hook_s[0] + HOOK),
        (front - 0.01, hook_s[0]),
    ]
    from boresight_case.geom import prism

    # Drawn in the (a, s) plane, extruded across y (F x D is +y).
    origin = L.grip_point(0, 0, ys[0])
    return prism(origin, F, D, pts, ys[1] - ys[0])


def _latch_cuts(fit: Fit) -> Part:
    """A slit behind the tongue and a gap at its free end, so it flexes."""
    (_, _), (y0, y1) = LATCH_NOTCH
    slit = grip_box(
        TONGUE_A - 2.0, TONGUE_A, y0 - 1.5, y1 + 5.0, BASE_S - 0.1, L.GRIP_LENGTH + 0.1
    )
    gap = grip_box(TONGUE_A - 2.0, 30, y0 - 1.5, y0, BASE_S - 0.1, L.GRIP_LENGTH + 0.1)
    return slit + gap


def holder_location(kind: str, s0: float) -> Location:
    """A cell holder with its cells along the grip's axis from `s0`, against
    the spine, centred across y."""
    _, _, height = HOLDERS[kind]
    return Location(
        Plane(origin=L.grip_point(s0, HOLDER_A0 + height / 2, 0), x_dir=D, z_dir=F)
    )


def _stop(fit: Fit, kind: str, s0: float) -> Part:
    """A plate on the holder's top end, and ramped lips on it and the base
    that the holder snaps past."""
    length, width, height = HOLDERS[kind]
    plate = _band(fit, s0 - 3.0, s0)
    lips = []
    front = HOLDER_A0 + height
    for s_face, sign in ((s0, 1), (BASE_S, -1)):
        # A lip 1 mm over the holder's end, sloping off toward the spine.
        from boresight_case.geom import prism

        pts = [
            (front - 2.0, s_face),
            (front + 0.01, s_face),
            (front + 0.01, s_face + sign * 1.0),
        ]
        origin = L.grip_point(0, 0, -(width / 2 - 2.0))  # F x D is +y
        lips.append(prism(origin, F, D, pts, width - 4.0))
    return plate + union(lips)


@cache
def drawer(fit: Fit, kind: str) -> Module:
    name = f"drawer-{kind}"
    m = Module(name)
    if kind in ("aa", "aaa", "18650"):
        length, width, height = HOLDERS[kind]
        s0 = BASE_S - length
        shape = _frame(fit) + (
            _stop(fit, kind, s0)
            if kind != "18650"
            else _band(fit, s0 - 2.0, s0, -30, -2.0)
        )
        if kind == "18650":
            shape = shape + _charger_mount(fit) - _charger_cuts(fit)
        m.add(bought(f"holder-{kind}", holder_location(kind, s0), "cell holder", name))
        m.fit(name, "cell holder")  # snapped past the lips
        if kind == "18650":
            m.add(bought("tp4056", charger_location(), "charger", name))
            m.fit(name, "charger")  # its port through the base
    else:
        shape = _frame(fit, top_a1=CABLE_A - 3.0) + _cable_posts(fit) - _cable_exit(fit)
    for i, a in enumerate(CONTACT_A):
        where = Location(
            Plane(
                origin=L.grip_point(TOP_S + CONTACT_PLATE[2], a, 0), x_dir=F, z_dir=-D
            )
        )
        m.add(bought("flat-contact", where, f"flat contact {'+-'[i]}", name))
    m.add(Printed(name, shape, UP, name, material=PETG, perimeters=3, infill=25))
    # Printed last so the module's printed part leads its purchased ones.
    m.printed.insert(0, m.printed.pop())
    return m


# -- the 18650 drawer's charger ---------------------------------------------


def charger_location() -> Location:
    """The TP4056 module standing on its edge: its PCB's back on a =
    TP4056_A, parts and port toward the front, port down through the base."""
    return Location(Plane(origin=L.grip_point(TP4056_S, TP4056_A, 0), x_dir=D, z_dir=F))


def _charger_mount(fit: Fit) -> Part:
    """A slotted block that holds the charger's top end."""
    c = fit.clearance
    half = TP4056[1] / 2
    edge = L.BAY_WIDTH / 2 - c
    block = grip_box(
        TP4056_A - 2.0,
        TP4056_A + TP4056[2] + 1.5,
        -half - 1.5,
        edge,
        TP4056_S - 3.0,
        TP4056_S + 2.0,
    )
    # A web beside the cell holder ties it to the spine.
    web = grip_box(
        -30,
        TP4056_A,
        HOLDERS["18650"][1] / 2 + c + 0.5,
        edge,
        TP4056_S - 3.0,
        TP4056_S + 2.0,
    )
    slot = grip_box(
        TP4056_A - c,
        TP4056_A + TP4056[2] + c,
        -half - c,
        half + c,
        TP4056_S - 0.01,
        TP4056_S + 3.0,
    )
    return ((block + web) & outline(fit)) - slot


def _charger_cuts(fit: Fit) -> Part:
    """The charger's PCB slot and USB-C port through the base."""
    c = fit.clearance
    pw, ph, _ = TP4056_PORT
    port_a = TP4056_A + TP4056[2]
    half = TP4056[1] / 2
    pcb = grip_box(
        TP4056_A - c,
        TP4056_A + TP4056[2] + c,
        -half - c,
        half + c,
        BASE_S - 0.5,
        BASE_S + 0.01,
    )
    port = grip_box(
        port_a - 0.3,
        port_a + ph + 0.3,
        -pw / 2 - 0.3,
        pw / 2 + 0.3,
        BASE_S - 1.0,
        L.GRIP_LENGTH + 1.0,
    )
    return pcb + port


# -- the tether drawer's cable -----------------------------------------------

POSTS = ((55.0, CABLE_Y - 5.0), (68.0, CABLE_Y + 3.5), (81.0, CABLE_Y - 5.0))  # s, y


def _cable_posts(fit: Fit) -> Part:
    """Three posts from the spine that the cable weaves between."""
    from boresight_case.geom import cylinder

    return union(
        cylinder(
            L.grip_point(s, SPINE_A - 0.01, y), tuple(F), 2.5, CABLE_A + 3.5 - SPINE_A
        )
        for s, y in POSTS
    )


def _cable_exit(fit: Fit) -> Part:
    from boresight_case.geom import teardrop

    return teardrop(
        L.grip_point(BASE_S - 0.5, CABLE_A, CABLE_Y), tuple(D), 2.6, 6.0, UP
    )


def cable_path() -> list[tuple[float, float, float]]:
    """The tether cable's centreline through the drawer, top to base."""
    # Straight down through the ceiling's hole until clear of its slope,
    # then back to the posts.
    pts = [
        (L.BAY_CEILING_S - 2.0, 14.0, CABLE_Y),
        (TOP_S + 4.0, 14.0, CABLE_Y),
        (TOP_S + 9.0, CABLE_A, CABLE_Y),
    ]
    for s, y in POSTS:
        side = 4.6 if y < CABLE_Y else -4.6
        pts.append((s, CABLE_A, y + side))
    pts.append((BASE_S - 2.0, CABLE_A, CABLE_Y))
    pts.append((L.GRIP_LENGTH + 10.0, CABLE_A, CABLE_Y))
    return [tuple(L.grip_point(s, a, y)) for s, a, y in pts]


__all__ = ["drawer", "outline", "cable_path", "Y"]
