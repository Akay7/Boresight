"""Every interface of the gun, placed. Both parts of a fit import it from
here, so each port, bolt and slide is defined once."""

from __future__ import annotations

from functools import cache

from boresight_case import layout as L
from boresight_case.geom import Z
from boresight_case.interfaces import (
    ModuleJoint,
    Peg,
    Port,
    ScrewFix,
    SlideFit,
    ThroughBolt,
)
from boresight_case.vendor import PI_HOLE_D, PI_HOLES, PICAM_HOLE_D, PICAM_HOLES

# -- ports: every end of the receiver and of a barrel ----------------------------

REAR_PORT = Port("rear port", L.RECEIVER_X[0], -1)  # takes the rear cap
RECEIVER_PORT = Port("receiver port", L.RECEIVER_X[1], +1)  # a barrel, or the nose


def barrel_port(k: int) -> Port:
    """The port at barrel k's muzzle end."""
    return Port(f"barrel {k + 1} port", L.barrel_x(k)[1], +1)


def front_port(barrels: int) -> Port:
    """The muzzle port: where the camera module or the nose goes."""
    return RECEIVER_PORT if barrels == 0 else barrel_port(barrels - 1)


def ports(barrels: int) -> list[Port]:
    return [REAR_PORT, RECEIVER_PORT] + [barrel_port(k) for k in range(barrels)]


# -- the grip --------------------------------------------------------------------

# The grip's tenon in the receiver's floor. Its through-bolt crosses the
# receiver's walls and a crush bar in the tenon.
GRIP_JOINT = ModuleJoint(
    name="grip joint",
    mouth=(L.GRIP_TOP.X, 0, L.FLOOR_Z),
    axis=Z,
    u=(1, 0, 0),
    opening=L.GRIP_JOINT,
    depth=L.GRIP_JOINT_DEPTH,
    screw_dir=(0, 1, 0),
    screw_at=4.0,
)
GRIP_BOLT = ThroughBolt("grip bolt", (L.GRIP_BOLT[0], 0, L.GRIP_BOLT[1]))
BACKSTRAP_BOLT = ThroughBolt(
    "backstrap bolt",
    tuple(L.grip_point(L.BACKSTRAP_BOLT_S, L.BOSS_A)),
    half=L.GRIP_WIDTH / 2,
)


def through_bolts(barrels: int) -> list[ThroughBolt]:
    """Every through-bolt of a gun with `barrels` barrels."""
    out = [b for p in ports(barrels) for b in p.bolts]
    return out + [GRIP_BOLT, BACKSTRAP_BOLT]


BAY_SLIDE = SlideFit(
    centre=tuple(L.grip_point(L.BAY_CEILING_S)),
    axis=tuple(L.GRIP_D),
    u=(0, 1, 0),
    size=(L.BAY_WIDTH, L.BAY_DEPTH),
    length=L.GRIP_LENGTH - L.BAY_CEILING_S,
    key=(6.0, 2.0),  # a rib down the bay's front wall
)

# The drawer's thumbscrew: up through the drawer's foot into a nut in the
# boss at the bottom of the grip's front. Clamps the foot and the boss
# under the nut.
THUMBSCREW_FIX = ScrewFix(
    "thumbscrew",
    entry=tuple(L.grip_point(L.GRIP_LENGTH + L.DRAWER_FOOT, L.THUMB_A)),
    direction=tuple(-L.GRIP_D),
    clamp=L.DRAWER_FOOT + 4.6,
    length=10.0,
)

# -- the trigger ---------------------------------------------------------------------

# Up through the trigger housing's top plate and the receiver's floor into
# a nut on the floor's inside. Its head is under the top plate, behind the
# blade, reached from below.
TRIGGER_BOLT = ScrewFix(
    "trigger bolt",
    entry=(L.TRIGGER_BOLT_X, L.TRIGGER_BOLT_Y, L.TRIGGER_BOLT_HEAD_Z),
    direction=Z,
    clamp=L.FLOOR_Z - L.TRIGGER_BOLT_HEAD_Z + L.WALL,
)

# The cable clamp's thumbscrew: up through the bar under the barrel and
# the barrel's floor into a nut on the floor's inside.
CLAMP_FIX = ScrewFix(
    "clamp thumbscrew",
    entry=(76.0, 4.5, L.FLOOR_Z - 9.0),
    direction=Z,
    clamp=9.0 + L.WALL,
    length=16.0,
)

# -- pegs -------------------------------------------------------------------------

PI_PLATE_FACE = L.plate_y(+1)[0]  # the Pi sled plate's inner face
STANDOFF = PI_PLATE_FACE - L.PI_PCB_Y  # sled plate to the Pi's underside


@cache
def pi_pegs() -> tuple[Peg, ...]:
    """Pegs from the sled plate through the Pi's four holes (the first
    barrel's coordinates)."""
    return tuple(
        Peg(
            base=(L.PI_X0 + hx, PI_PLATE_FACE, L.PI_Z0 + hy),
            axis=(0, -1, 0),
            hole_d=PI_HOLE_D,
            length=1.4 + 1.0,
            standoff_d=4.0,  # clear of the rails' lips below
            standoff_h=STANDOFF,
        )
        for hx, hy in PI_HOLES
    )


def picam_pegs() -> tuple[Peg, ...]:
    """Pegs from the camera module's front plate back through the camera's
    holes (the first barrel's coordinates)."""
    face = L.BARREL_LEN
    standoff = face - (L.PICAM_PCB_BACK_X + 1.0)
    return tuple(
        Peg(
            base=(face, hy, hz),
            axis=(-1, 0, 0),
            hole_d=PICAM_HOLE_D,
            length=1.0 + 1.0,
            standoff_d=4.0,
            standoff_h=standoff,
        )
        for hy, hz in PICAM_HOLES
    )
