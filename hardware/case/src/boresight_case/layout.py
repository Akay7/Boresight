"""Where everything sits: the gun's one set of dimensions.

Coordinates as in `geom`: x forward along the camera axis (the bore), y to
the gun's left, z up, in mm; the bore is the x axis. Every module reads its
position from here, so moving one module moves its bolts, its covers and
its checks with it.

The gun is bones (receiver, barrels, grip, rear cap) joined at ports, and
modules inside them. Every end of the receiver and of a barrel is the same
port: a 31 x 45 opening, 12 mm deep, keyed by a rib under its top wall,
with two through-bolts 6 mm in from its mouth at z = +12 and -12.

    rear cap   receiver               barrel 1          barrel 2       nose
    -106..-100 -100 .............. 0 .......... 100 ........... 200 .. +36
       port zones: the outer 12 mm of each end; carriers ride the rails
       between them, never across a joint
                 \\ grip (raked 18 degrees), the trigger in a pocket at
                  \\ the top of its front, the drawer in its bay
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
BARREL_LEN = 100.0
REAR_CAP_PLATE = (-106.0, -100.0)

# -- the port: every bone end ------------------------------------------------------
PORT_DEPTH = 12.0  # how far a tenon (or a camera module) goes in
PORT_BOLT_AT = 6.0  # the bolts, in from the mouth
PORT_BOLT_Z = (12.0, -12.0)
KEY_RIB = (6.0, 2.0)  # under the top wall: width across y, depth
CRUSH_R = 3.5  # a crush tube's outside radius


def barrel_x(k: int) -> tuple[float, float]:
    """Barrel k's span (k = 0 is the first, joined to the receiver)."""
    return (k * BARREL_LEN, (k + 1) * BARREL_LEN)


def muzzle_x(barrels: int) -> float:
    """The muzzle port's mouth: the front of the last bone."""
    return barrels * BARREL_LEN


def port_bolt_x(mouth: float, facing: int) -> float:
    """The bolts of the port whose mouth is at `mouth`; `facing` is +1 for a
    port opening forward (its bone lies behind it), -1 for one opening
    backward."""
    return mouth - facing * PORT_BOLT_AT


# -- rails and carriers --------------------------------------------------------------
# C-channels on both inner side walls hold a 2 mm plate's top and bottom
# edges. A plate stands 0.25 mm off the wall's inside face.
RAIL_Z = (-14.5, 19.5)  # the plate's bottom and top edges
PLATE_T = 2.0
PLATE_OFF = 0.25  # between the plate and the wall
# Each bone's run: where carriers may ride, between its two port zones.
# The barrel's first 5 mm hold its tenon's root.
RECEIVER_RUN = (RECEIVER_X[0] + PORT_DEPTH, RECEIVER_X[1] - PORT_DEPTH)  # -88..-12
BARREL_RUN = (5.0, BARREL_LEN - PORT_DEPTH)  # 5..88, from the barrel's rear


def plate_y(side: int) -> tuple[float, float]:
    """A carrier plate's two faces (inner, outer) on the left (+1) or
    right (-1) wall."""
    outer = side * (IN_HALF_W - PLATE_OFF)
    inner = outer - side * PLATE_T
    return (inner, outer)


# -- the hub, the feedback carrier, the buttons --------------------------------------
HUB_X = (-88.0, -46.0)  # left rails, above the grip
SWITCH_AT = (-80.0, 0.0)  # x, z of the slide switch's knob, left wall
POWER_LED_AT = (-86.0, 8.0)  # beside the switch
STATUS_LED_AT = (-77.0, 8.0)
BUTTONS_X = (-46.0, -24.0)  # left rails, ahead of the hub
BUTTON_AT = ((-40.0, 0.0), (-30.0, 0.0))  # Start, Select: x, z
FEEDBACK_X = (-52.0, -12.0)  # right rails, ahead of the hub
SPACER_X = (-88.0, -52.0)  # right rails, behind the feedback carrier

# -- the Pi kit, in the last barrel (x from that barrel's rear) ------------------------
PI_SLED_X = BARREL_RUN  # 5..88
PI_X0 = 8.0  # the Pi's micro-SD end; its camera end is at 73
PI_Z0 = -14.4  # the Pi's port edge (bottom), ports facing down
PI_PCB_Y = 10.2  # the Pi PCB's underside (left); its components face -y
WINDOW_X = (5.0, 68.0)  # the barrel floor's window, from the barrel's rear
WINDOW_Y = (-4.0, 13.0)
SOC_VENT_X = (29.0, 47.0)  # vent slots over the processor, right wall
PICAM_PCB_BACK_X = 88.5  # the camera PCB's back face, from the barrel's rear
FLANGE_T = 2.5  # the camera module's front plate, ahead of the muzzle

# -- the ESP32-CAM nose (x from the muzzle) --------------------------------------------
NOSE_BOARD_BACK = 24.0  # the board's back face, ahead of the muzzle
NOSE_LEN = 36.0  # the nose's body, ahead of the muzzle

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
GRIP_JOINT = (30.0, IN_W)  # the tenon's socket in the floor: along x, across y
GRIP_JOINT_DEPTH = 8.0
GRIP_BOLT = (-80.0, -21.0)  # x, z of the grip joint's through-bolt
# The boss down the grip's back that the backstrap bolt crosses, and the
# boss at the bottom of its front that holds the drawer thumbscrew's nut.
# Along the axis (s), and toward the front (a).
BACK_BOSS_S = (84.0, GRIP_LENGTH)
BACK_BOSS_A = (-GRIP_DEPTH / 2 - 7.5, -GRIP_DEPTH / 2)
BACKSTRAP_BOLT_S = 94.0
BOSS_A = -GRIP_DEPTH / 2 - 3.75  # the backstrap bolt's line
FRONT_BOSS_S = (106.0, GRIP_LENGTH)
FRONT_BOSS_A = (GRIP_DEPTH / 2, GRIP_DEPTH / 2 + 7.5)
FRONT_BOSS_Y = 6.0  # half its width
THUMB_A = GRIP_DEPTH / 2 + 3.75  # the thumbscrew's line
DRAWER_FOOT = 3.0  # the drawer's foot below the grip's base

# -- the trigger, in the grip's front pocket ------------------------------------------
# Side view: the housing's top against the receiver's underside, its rear
# in a pocket in the grip's front, its front reaching forward under the
# receiver. The blade hangs from the pivot bolt; its tail, above the
# pivot, presses the switch in front of it. An arm from the blade reaches
# forward under the switch to the stop screw, which comes up from below.
TRIGGER_X = (-67.0, -8.0)
TRIGGER_Z = (-76.0, FLOOR_Z)
TRIGGER_HALF_W = 13.0
TRIGGER_WALL = 2.5
TRIGGER_TOP_T = 3.0
PIVOT = Vector(-42.0, 0.0, -54.0)
LEVER_W = 6.0  # along y
CONTACT_R = 18.0  # the switch contact (the tail's pad) above the pivot
ARM_Z = (-6.0, -3.5)  # the stop arm's underside and top, about the pivot
STOP_X = -13.0  # the stop screw, up from below into the arm's underside
STOP_Y = 0.0
SPRING_R = 14.0  # the return spring meets the blade's back here, below it
SPRING_WALL_X = (-57.5, -54.5)  # the wall behind the blade that seats it
FRONT_BLOCK_X = (-17.5, TRIGGER_X[1])
FRONT_BLOCK_BOTTOM = TRIGGER_Z[0]
# The mounting bolt: up through the top plate behind the blade into a nut
# on the receiver floor's inside, its head reached from below past the blade.
TRIGGER_BOLT_X = -48.0
TRIGGER_BOLT_Y = -10.75  # in the right side wall, beside either switch
TRIGGER_BOLT_HEAD_Z = FLOOR_Z - TRIGGER_TOP_T


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


def grip_front_x(z: float) -> float:
    """The grip's front face (the bone) at height `z`."""
    a = GRIP_DEPTH / 2
    s = (z - GRIP_TOP.Z - GRIP_F.Z * a) / GRIP_D.Z
    return grip_point(s, a).X


def grip_back_x(z: float) -> float:
    """The grip's back face (the bone, not a cover) at height `z`."""
    a = -GRIP_DEPTH / 2
    # z = GRIP_TOP.Z + D.Z s + F.Z a
    s = (z - GRIP_TOP.Z - GRIP_F.Z * a) / GRIP_D.Z
    return grip_point(s, a).X


# Each switch plate's default stop: the switch's travel, in mm, at the
# tail's pad when the trigger reaches the stop screw. MX: actuates at 2.0,
# bottoms at 4.0. Microswitch (pressed at its lever's tip): operates at
# 1.6, bottoms at 2.4.
STOP_TRAVEL = {"mx": 3.0, "microswitch": 2.0}
