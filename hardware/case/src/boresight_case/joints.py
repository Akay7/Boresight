"""Every interface of the gun, placed. Both parts of a fit import it from
here, so each joint, attachment point and slide is defined once."""

from __future__ import annotations

from boresight_case import layout as L
from boresight_case.geom import X, Y, Z
from boresight_case.interfaces import (
    AttachmentPoint,
    ModuleJoint,
    Peg,
    ScrewFix,
    SlideFit,
)
from boresight_case.vendor import PI_HOLE_D, PI_HOLES, PICAM_HOLE_D, PICAM_HOLES

# -- module joints: barrel, rear cap and grip into the receiver -----------------

BARREL_JOINT = ModuleJoint(
    name="barrel joint",
    mouth=(L.RECEIVER_X[1], 0, 0),
    axis=(-1, 0, 0),
    u=Y,
    opening=(L.IN_W, L.IN_H),
    depth=L.JOINT_DEPTH,
    screw_dir=Y,
    screw_at=6.0,
    screw_offset=12.0,  # across is -z: the screw sits at z = -12
)

REAR_CAP_JOINT = ModuleJoint(
    name="rear cap joint",
    mouth=(L.RECEIVER_X[0], 0, 0),
    axis=X,
    u=Y,
    opening=(L.IN_W, L.IN_H),
    depth=L.REAR_CAP_TENON,
    screw_dir=Y,
    screw_at=4.0,
    screw_offset=-12.0,  # across is +z
)

GRIP_JOINT = ModuleJoint(
    name="grip joint",
    mouth=(L.GRIP_TOP.X, 0, L.FLOOR_Z),
    axis=Z,
    u=X,
    opening=L.GRIP_JOINT,
    depth=L.GRIP_JOINT_DEPTH,
    screw_dir=Y,
    screw_at=4.5,
)

MODULE_JOINTS = (BARREL_JOINT, REAR_CAP_JOINT, GRIP_JOINT)

# -- skin attachment points (on the core's outer faces) -------------------------

_GRIP_HOOK_STEM = (4.0, 2.4)

ATTACHMENTS: dict[tuple[str, str], AttachmentPoint] = {
    ("barrel", "left"): AttachmentPoint(
        "barrel-left", Y, (10, L.HALF_W, 10), (64, L.HALF_W, -10), X
    ),
    ("barrel", "right"): AttachmentPoint(
        "barrel-right", (0, -1, 0), (10, -L.HALF_W, 10), (64, -L.HALF_W, -10), X
    ),
    # The left wall carries the Pi's sled: its points sit where the sled
    # plate is notched for them.
    ("receiver", "left"): AttachmentPoint(
        "receiver-left",
        Y,
        (-83, L.HALF_W, 21),
        (-20, L.HALF_W, 0),
        X,
        boss=(9.0, 6.0),  # short, so the Pi's standoff below keeps its plate
    ),
    ("receiver", "right"): AttachmentPoint(
        "receiver-right", (0, -1, 0), (-80, -L.HALF_W, 8), (-25, -L.HALF_W, 8), X
    ),
    ("grip", "left"): AttachmentPoint(
        "grip-left",
        Y,
        tuple(L.grip_point(6, 0, L.GRIP_WIDTH / 2)),
        tuple(L.grip_point(104, L.GRIP_DEPTH / 2, 1.6)),
        tuple(-L.GRIP_D),
        stem=_GRIP_HOOK_STEM,
        backed=True,
        hook_normal=tuple(L.GRIP_F),
    ),
    ("grip", "right"): AttachmentPoint(
        "grip-right",
        (0, -1, 0),
        tuple(L.grip_point(6, 0, -L.GRIP_WIDTH / 2)),
        tuple(L.grip_point(104, L.GRIP_DEPTH / 2, -1.6)),
        tuple(-L.GRIP_D),
        stem=_GRIP_HOOK_STEM,
        backed=True,
        hook_normal=tuple(L.GRIP_F),
    ),
}


# -- slides ----------------------------------------------------------------------

BULKHEAD_SLIDE = SlideFit(
    centre=(L.BULKHEAD_X[0], 0, 0),
    axis=X,
    u=Y,
    size=(L.IN_W, L.IN_H),
    length=L.BULKHEAD_X[1] - L.BULKHEAD_X[0],
    key=(
        6.0,
        2.0,
    ),  # a rib under the barrel's top wall: the bulkhead can't go in upside down
)

BAY_SLIDE = SlideFit(
    centre=tuple(L.grip_point(L.BAY_CEILING_S)),
    axis=tuple(L.GRIP_D),
    u=Y,
    size=(L.BAY_WIDTH, L.BAY_DEPTH),
    length=L.GRIP_LENGTH - L.BAY_CEILING_S,
    key=L.KEY_RIB,  # a rib down the bay's front wall
)

# -- screws that are not module joints -----------------------------------------------

# Up through the barrel's floor into a nut in the bulkhead's tail. Clamps the
# barrel wall, the clearance and the tail's 2 mm floor.
BULKHEAD_SCREW = ScrewFix(
    "bulkhead screw",
    entry=(L.BULKHEAD_SCREW_X, 4.5, L.FLOOR_Z),
    direction=Z,
    clamp=L.WALL + 0.25 + 2.0,
)

# Up through the cassette's front wall (head recessed 1.5 mm) and the
# receiver's floor into a nut on the floor's inside.
CASSETTE_SCREW = ScrewFix(
    "cassette screw",
    entry=(L.CASSETTE_SCREW.X, L.CASSETTE_SCREW.Y, L.CASSETTE_SCREW.Z + 1.5),
    direction=Z,
    clamp=(L.FLOOR_IN - (L.CASSETTE_SCREW.Z + 1.5)),
)

# -- pegs -------------------------------------------------------------------------

STANDOFF = L.SLED_PLATE_Y[0] - L.PI_PCB_Y  # sled plate to the Pi's underside


def pi_pegs() -> list[Peg]:
    """Pegs from the sled plate through the Pi's four holes."""
    return [
        Peg(
            base=(L.PI_X0 + hx, L.SLED_PLATE_Y[0], L.PI_Z0 + hy),
            axis=(0, -1, 0),
            hole_d=PI_HOLE_D,
            length=1.4 + 1.0,
            standoff_d=5.0,
            standoff_h=STANDOFF,
        )
        for hx, hy in PI_HOLES
    ]


def picam_pegs() -> list[Peg]:
    """Pegs from the bulkhead flange's back through the camera's holes."""
    standoff = L.FLANGE_X[0] - (L.PICAM_PCB_BACK_X + 1.0)
    return [
        Peg(
            base=(L.FLANGE_X[0], hy, hz),
            axis=(-1, 0, 0),
            hole_d=PICAM_HOLE_D,
            length=1.0 + 1.0,
            standoff_d=4.0,
            standoff_h=standoff,
        )
        for hy, hz in PICAM_HOLES
    ]
