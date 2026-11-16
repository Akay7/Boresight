"""The receiver: the hub every other module joins.

A box tube from the rear cap (x = -100) to the barrel (x = 0), printed
standing on its rear end, so its walls rise straight and its two ends are
the barrel's and the rear cap's sockets. Underneath: the grip's socket,
the trigger cassette's rails and screw boss. Inside: the Pi sled's rails.
"""

from __future__ import annotations

from functools import cache

from build123d import Part

from boresight_case import layout as L
from boresight_case.geom import X, box, opening, prism, side_profile, teardrop, union
from boresight_case.interfaces import Fit
from boresight_case.joints import (
    ATTACHMENTS,
    BARREL_JOINT,
    CASSETTE_SCREW,
    GRIP_JOINT,
    REAR_CAP_JOINT,
)
from boresight_case.model import Module, Printed, bought

UP = X  # printed standing on its rear end

# The grip socket's front face slopes at 45 degrees, from the floor's
# underside to the top of the rib inside, so it prints without support and
# the grip's tenon wedges against it.
GRIP_SOCKET_X = (L.GRIP_TOP.X - L.GRIP_JOINT[0] / 2, L.GRIP_TOP.X + L.GRIP_JOINT[0] / 2)
GRIP_TENON_TOP = L.FLOOR_Z + L.GRIP_JOINT_DEPTH
FRONT_RIB_X = -54.5  # clear of the Pi's USB plug and its cable


def _grip_socket(fit: Fit) -> tuple[Part, Part]:
    """(material to add inside: the two ribs, cut: the floor opening)."""
    x0, x1 = GRIP_SOCKET_X
    w = L.IN_HALF_W
    rise = GRIP_TENON_TOP - L.FLOOR_IN
    # Rear rib: a vertical face at x0 for the tenon's back, sloping away.
    rear = side_profile(
        [(x0 - rise, L.FLOOR_IN), (x0, L.FLOOR_IN), (x0, GRIP_TENON_TOP)], -w, w
    )
    # Front rib: its back face continues the floor opening's 45-degree edge.
    f_bottom = x1 - L.WALL  # where the slope crosses the floor's inner face
    front = side_profile(
        [
            (f_bottom, L.FLOOR_IN),
            (FRONT_RIB_X, L.FLOOR_IN),
            (FRONT_RIB_X, GRIP_TENON_TOP),
            (f_bottom - rise, GRIP_TENON_TOP),
        ],
        -w,
        w,
    )
    cut = side_profile(
        [
            (x0, L.FLOOR_Z - 1),
            (x1 + 1, L.FLOOR_Z - 1),
            (x1, L.FLOOR_Z),
            (f_bottom, L.FLOOR_IN),
            (x0, L.FLOOR_IN),
        ],
        -w,
        w,
    )
    return rear + front, cut


def _sled_rails(fit: Fit) -> Part:
    """C-channels on the left wall holding the sled plate's top and bottom
    edges, open at the rear (the sled slides in with the rear cap off)."""
    c = fit.clearance
    x0, x1 = L.SLED_X[0] + 0.5, L.SLED_X[1]
    wall = L.IN_HALF_W
    plate_front = L.SLED_PLATE_Y[0] - c
    lip = -1.0
    rails = []
    for edge, outward in ((L.SLED_Z[1], 1), (L.SLED_Z[0], -1)):
        back = edge + outward * c
        top = back + outward * 2.0
        # The bar beyond the plate's edge, from the wall to the lip.
        z0, z1 = sorted((back, top))
        bar = _rail_prism(x0, x1, wall, plate_front + lip, z0, z1)
        # The lip in front of the plate, 1.5 mm over its face.
        zl0, zl1 = sorted((edge - outward * 1.5, top))
        lip_part = _rail_prism(x0, x1, plate_front, plate_front + lip, zl0, zl1)
        rails += [bar, lip_part]
    # A gap in the top lip where the sled's front clip reaches over.
    gap = box(
        -27.0,
        -23.5,
        plate_front + lip - 0.1,
        plate_front + 0.1,
        L.SLED_Z[1] - 2.0,
        L.SLED_Z[1] + 3.0,
    )
    return union(rails) - gap


def _rail_prism(
    x0: float, x1: float, y0: float, y1: float, z0: float, z1: float
) -> Part:
    """A rail along x whose rear end slopes at 45 degrees back to the wall,
    so its end prints without support in the receiver's orientation."""
    depth = abs(y1 - y0)
    lo, hi = min(y0, y1), max(y0, y1)
    # Drawn in the x-y plane, extruded along z.
    wall_y = lo if y0 < y1 else hi
    far_y = hi if y0 < y1 else lo
    pts = [(x0, wall_y), (x1, wall_y), (x1, far_y), (x0 + depth, far_y)]
    return prism((0, 0, z0), X, (0, 1, 0), pts, z1 - z0)


def _vents() -> Part:
    """Slots in the right wall and the top over the Pi's processor."""
    x0, x1 = L.SOC_VENT_X
    cx, length = (x0 + x1) / 2, x1 - x0
    side = [
        opening((cx, -L.HALF_W + L.WALL / 2, z), (0, 1, 0), 2.5, length, L.WALL + 1, UP)
        for z in (-4.0, 0.5, 5.0, 9.5, 14.0)
    ]
    top = [
        opening((cx, y, L.HALF_H - L.WALL / 2), (0, 0, 1), 2.5, length, L.WALL + 1, UP)
        for y in (-8.0, -4.0, 0.0, 4.0)
    ]
    return union(side + top)


def _cassette_mount(fit: Fit) -> tuple[Part, Part]:
    """(add: rails under the floor that locate the cassette across y, and
    the nut boss inside; cut: the screw hole, nut pocket and lead hole)."""
    c = fit.clearance
    x0, x1 = L.CASSETTE_X
    w = L.CASSETTE_HALF_W + c
    rails = union(
        side_profile(
            [
                (x0, L.FLOOR_Z),
                (x1, L.FLOOR_Z),
                (x1, L.FLOOR_Z - 2.0),
                (x0 + 2.0, L.FLOOR_Z - 2.0),
            ],
            y0,
            y1,
        )
        for y0, y1 in ((w, w + 2.0), (-w - 2.0, -w))
    )
    boss = CASSETTE_SCREW.boss(UP, size=7.0, height=5.0)
    cuts = CASSETTE_SCREW.clear_hole(
        UP, depth=L.FLOOR_IN - CASSETTE_SCREW.entry[2] - 0.01
    )
    cuts = cuts + CASSETTE_SCREW.nut_cuts(fit, UP)
    # The trigger lead's plug comes up through here.
    lead = opening(
        (-44.0, -3.0, L.FLOOR_Z + L.WALL / 2), (0, 0, 1), 7.0, 7.5, L.WALL + 1, UP
    )
    return rails + boss, cuts + lead


@cache
def receiver(fit: Fit) -> Module:
    x0, x1 = L.RECEIVER_X
    tube = box(x0, x1, -L.HALF_W, L.HALF_W, -L.HALF_H, L.HALF_H) - box(
        x0 - 1, x1 + 1, -L.IN_HALF_W, L.IN_HALF_W, -L.IN_HALF_H, L.IN_HALF_H
    )
    ribs, socket = _grip_socket(fit)
    mount, mount_cuts = _cassette_mount(fit)
    bosses = union(
        ATTACHMENTS[("receiver", side)].core_boss(UP) for side in ("left", "right")
    )
    body = tube + ribs + mount + bosses + _sled_rails(fit)
    cuts = [socket, mount_cuts, _vents()]
    cuts += [j.host_cuts(fit, UP) for j in (BARREL_JOINT, REAR_CAP_JOINT, GRIP_JOINT)]
    cuts += [ATTACHMENTS[("receiver", s)].core_cuts(fit, UP) for s in ("left", "right")]
    shape = body - union(cuts)

    m = Module("receiver")
    m.add(Printed("receiver", shape, UP, "receiver", perimeters=4, infill=30))
    for side in ("left", "right"):
        a = ATTACHMENTS[("receiver", side)]
        m.add(_nut_or_insert(fit, a, side))
        m.fit("receiver", m.bought[-1].label)
    m.add(_cassette_nut(fit))
    m.fit("receiver", m.bought[-1].label)
    return m


def _nut_or_insert(fit: Fit, a, side: str):
    if fit.fastener == "insert":
        return bought(
            "m3-insert",
            a.insert_location(),
            f"insert, receiver skin {side}",
            "receiver",
        )
    return bought(
        "m3-nut", a.nut_location(UP), f"nut, receiver skin {side}", "receiver"
    )


def _cassette_nut(fit: Fit):
    if fit.fastener == "insert":
        return bought(
            "m3-insert",
            CASSETTE_SCREW.insert_location(),
            "insert, cassette screw",
            "receiver",
        )
    return bought(
        "m3-nut",
        CASSETTE_SCREW.nut_location(fit, UP),
        "nut, cassette screw",
        "receiver",
    )


__all__ = ["receiver", "teardrop"]
