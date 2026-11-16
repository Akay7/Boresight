"""Where everything sits: the gun's one set of dimensions.

Coordinates as in `geom`: x forward along the camera axis (the bore), y to
the gun's left, z up, in mm; the bore is the x axis. Every module reads its
position from here, so moving one module moves its joints, its skins and
its checks with it.

    rear cap   receiver                      barrel           bulkhead
    -106..-100 -100 ........................ 0 ............ 100 .. 102.5
                 \\ grip (raked 18 degrees)   trigger cassette under the
                  \\  at the receiver's rear   receiver, -48 .. -14
"""

from __future__ import annotations

import math

from build123d import Vector

# -- the body: receiver and barrel share one box section ---------------------
WALL = 2.5
BODY_W = 36.0  # outside, across y
BODY_H = 50.0  # outside, z
IN_W = BODY_W - 2 * WALL  # 31
IN_H = BODY_H - 2 * WALL  # 45
HALF_W = BODY_W / 2  # 18: the body's flank plane
HALF_H = BODY_H / 2  # 25
IN_HALF_W = IN_W / 2  # 15.5
IN_HALF_H = IN_H / 2  # 22.5
FLOOR_Z = -HALF_H  # the receiver's underside
FLOOR_IN = -IN_HALF_H  # the floor's inner face

RECEIVER_X = (-100.0, 0.0)
BARREL_X = (0.0, 100.0)
JOINT_DEPTH = 12.0  # the barrel's tenon inside the receiver
REAR_CAP_PLATE = (-106.0, -100.0)
REAR_CAP_TENON = 8.0  # inside the receiver, -100 .. -92

# -- the camera bulkhead: a flange on the muzzle and a body in the barrel ------
FLANGE_X = (100.0, 102.5)
FLANGE_SIZE = (BODY_W - 1.0, BODY_H - 1.0)  # inside the body's outline
BULKHEAD_X = (86.0, 100.0)  # the body that plugs into the barrel
BULKHEAD_TAIL_X = 76.0  # the lower extension carrying the screw boss
BULKHEAD_SCREW_X = 80.0
BULKHEAD_WALL = 1.6
LENS_FRONT_X = 102.3  # the ESP32-CAM's lens front, just inside the flange

# -- the Pi kit --------------------------------------------------------------------
PI_X0 = -85.0  # the Pi's micro-SD end; its camera end is at -20
PI_Z0 = -12.5  # the Pi's port edge (bottom)
PI_PCB_Y = 10.2  # the Pi PCB's underside; its components face -y
SLED_PLATE_Y = (13.2, 15.25)  # on the left wall
SLED_X = (-91.75, -12.25)  # between the two tenons
SLED_Z = (-14.5, 19.5)
PICAM_PCB_BACK_X = 88.5  # the camera PCB's back face, both modules
SOC_VENT_X = (-64.0, -46.0)  # vent slots over the processor, right wall and top

# -- the grip ------------------------------------------------------------------------
GRIP_RAKE_DEG = 18.0
GRIP_TOP = Vector(-71.0, 0.0, FLOOR_Z)  # the grip axis meets the receiver's underside
_r = math.radians(GRIP_RAKE_DEG)
GRIP_D = Vector(-math.sin(_r), 0.0, -math.cos(_r))  # down the grip axis
GRIP_F = Vector(math.cos(_r), 0.0, -math.sin(_r))  # toward the grip's front
GRIP_DEPTH = 41.5  # outside, front to back (along GRIP_F)
GRIP_WIDTH = 37.2  # outside, across y
GRIP_WALL = 2.5
GRIP_LENGTH = 118.0  # along the axis from GRIP_TOP to the base
GRIP_TOP_S = -12.0  # the grip's solid starts above GRIP_TOP, then is cut at z = -25
BAY_DEPTH = 36.5  # along GRIP_F
BAY_WIDTH = 32.2  # along y
BAY_CEILING_S = 24.0  # the contact flat's underside
CEILING_FLAT = 10.0  # the flat's width across y: the longest bridge
CEILING_T = 3.0
KEY_RIB = (6.0, 2.0)  # the bay's key rib, at the front: width across y, depth
GRIP_JOINT = (30.0, IN_W)  # the tenon's socket in the floor: along x, across y
GRIP_JOINT_DEPTH = 8.0
GRIP_SCREW_X = -71.0

# -- the trigger cassette ------------------------------------------------------------
CASSETTE_X = (-48.0, -14.0)
CASSETTE_Z = (-67.5, FLOOR_Z)
CASSETTE_HALF_W = 11.0
CASSETTE_WALL = 2.5
CASSETTE_TOP_T = 3.0
PIVOT = Vector(-23.5, 0.0, -35.0)
LEVER_T = 5.0  # along x
LEVER_W = 6.0  # along y
CONTACT_R = 17.0  # the switch contact (the lever's pad) below the pivot
SPRING_R = 28.5
STOP_R = 5.0  # the stop screw meets the upper arm here, above the pivot
FRONT_WALL_X = (-19.0, -14.0)
FRONT_WALL_Z = (-32.5, FLOOR_Z)
CASSETTE_SCREW = Vector(-16.5, 5.5, -32.5)  # head's underside, screw goes +z
PLATE_X = (-39.1, -36.1)  # the switch plate: 3 mm; the MX web is its back 1.5 mm
SPRING_SEAT_X = -33.5


def grip_point(s: float, a: float = 0.0, y: float = 0.0) -> Vector:
    """A point `s` down the grip axis, `a` toward its front, `y` across."""
    return GRIP_TOP + GRIP_D * s + GRIP_F * a + Vector(0, y, 0)


def grip_outline(
    extra: float, bottom: float = GRIP_LENGTH - 0.1
) -> list[tuple[float, float]]:
    """The grip's side view (x, z), grown by `extra` front and back, from
    above the receiver's underside (trim it there) to `bottom` down the
    axis."""
    a = GRIP_DEPTH / 2 + extra
    top = -a * math.tan(_r) - 3.0
    pts = []
    for s, aa in ((top, -a), (top, a), (bottom, a), (bottom, -a)):
        p = grip_point(s, aa)
        pts.append((p.X, p.Z))
    return pts


def grip_top_x(a: float) -> float:
    """Where the line at `a` across the grip meets the receiver's underside."""
    return GRIP_TOP.X + a / math.cos(_r)


# Each switch plate's default stop: the switch's travel, in mm, at the
# lever's pad when the trigger reaches the stop screw. MX: actuates at 2.0,
# bottoms at 4.0. Microswitch (pressed at its lever's tip): operates at
# 1.6, bottoms at 2.4.
STOP_TRAVEL = {"mx": 3.0, "microswitch": 2.0}
