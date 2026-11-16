"""What every skin style shares: how a silhouette becomes skin parts.

A style draws, for each section (barrel, receiver, grip), the gun's
outline in side view. Each half (left, right) is that outline extruded
from just off the midplane out past the core's flank, its outer edge
chamfered at 45 degrees. From it come away: the core itself, extruded
through the gun (so every face toward the core faces up when the skin
prints flank-down, and nothing overhangs), every keep-out zone, and the
section's neighbours. Then each half gets its attachment point's hook and
screw hole.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from build123d import Location, Part, Plane, Polygon, extrude, mirror

from boresight_case import layout as L
from boresight_case.geom import X, Z, box, frame, side_profile, union
from boresight_case.interfaces import SKIN_T, Fit
from boresight_case.joints import ATTACHMENTS
from boresight_case.keepouts import zones
from boresight_case.model import Module, Printed, bought

Pts = list[tuple[float, float]]
GAP_Y = 0.2  # each half stops this short of the midplane
FLANK = {
    "barrel": L.HALF_W + SKIN_T,
    "receiver": L.HALF_W + SKIN_T,
    "grip": L.GRIP_WIDTH / 2 + SKIN_T,
}
GRIP_FRONT_X_AT_TOP = L.grip_top_x(L.GRIP_DEPTH / 2)
SPLIT_X = L.CASSETTE_X[0] - 0.6  # between the grip skins and the trigger housing
SIDES = ("left", "right")
UP = {"left": (0, -1, 0), "right": (0, 1, 0)}  # printed flank down


@dataclass
class Accent:
    """A separate decorative part on a skin, with press-fit pegs into holes
    through it."""

    name: str
    shape: Part  # in gun coordinates, pegs included
    holes: Part  # what it needs cut from the skins
    up: tuple[float, float, float]


@dataclass
class Style:
    """A style's drawing: an outline per section, and what it adds."""

    outlines: dict[str, list[Pts]]  # unioned polygons, side view (x, z)
    chamfer: float
    removals: dict[str, Part] = field(
        default_factory=dict
    )  # per section, cut from both halves
    flank_cuts: dict[str, Callable[[str], Part]] = field(
        default_factory=dict
    )  # per section and side
    accents: list[Accent] = field(default_factory=list)


def grip_outline(extra: float = SKIN_T, bottom: float = L.GRIP_LENGTH - 0.1) -> Pts:
    return L.grip_outline(extra, bottom)


def _xz(points: Pts, y: float) -> Part:
    """A face in the plane y = const, drawn in (x, z)."""
    return frame((0, y, 0), X, Z) * Polygon(*points, align=None)


def half_shell(polys: list[Pts], flank: float, chamfer: float) -> Part:
    """The left half's raw solid: each outline from GAP_Y to the flank, the
    last `chamfer` of it tapering at 45 degrees."""

    # One face per section, so a thin feature merged into its neighbour
    # survives the chamfer's inward offset.
    def merged(y: float):
        faces = [_xz(pts, y) for pts in polys]
        out = faces[0]
        for f in faces[1:]:
            out = out + f
        return out

    try:
        body = extrude(merged(GAP_Y), amount=flank - chamfer - GAP_Y, dir=(0, 1, 0))
        cap = extrude(merged(flank - chamfer), amount=chamfer, dir=(0, 1, 0), taper=45)
    except RuntimeError:
        # The taper's offset failed on an awkward outline: chamfer the
        # outer edges of the full extrusion instead.
        from build123d import Axis
        from build123d import chamfer as chamfer_edges

        full = extrude(merged(GAP_Y), amount=flank - GAP_Y, dir=(0, 1, 0))
        edges = full.edges().filter_by_position(Axis.Y, flank - 0.01, flank + 0.01)
        return chamfer_edges(edges, chamfer)
    if cap.bounding_box().max.Y < flank - 0.01:
        raise AssertionError("chamfer taper went the wrong way")
    return body + cap


# -- the core every skin wraps -----------------------------------------------------


def core_cavity() -> Part:
    """The core's side view extruded through the gun, each part out to its
    own flank: whatever lies inside it is the core's, not a skin's."""
    x0, x1 = L.RECEIVER_X
    hw, hh = L.HALF_W, L.HALF_H
    pieces = [
        side_profile(
            [
                (L.REAR_CAP_PLATE[0], -hh),
                (L.BARREL_X[1], -hh),
                (L.BARREL_X[1], hh),
                (L.REAR_CAP_PLATE[0], hh),
            ],
            -hw,
            hw,
        ),
        box(*L.FLANGE_X, -hw, hw, -hh, hh),
        # The cassette, functional: skins keep half a millimetre off it.
        box(
            L.CASSETTE_X[0] - 0.5,
            L.CASSETTE_X[1] + 0.5,
            -L.CASSETTE_HALF_W - 0.5,
            L.CASSETTE_HALF_W + 0.5,
            L.CASSETTE_Z[0] - 0.5,
            L.FLOOR_Z,
        ),
        # The rails under the receiver's floor that locate it.
        box(L.CASSETTE_X[0], L.CASSETTE_X[1], -13.5, 13.5, L.FLOOR_Z - 2.0, L.FLOOR_Z),
        side_profile(
            grip_outline(0.0, L.GRIP_LENGTH), -L.GRIP_WIDTH / 2, L.GRIP_WIDTH / 2
        ),
    ]
    return union(pieces)


def regions() -> dict[str, Part]:
    """Where each section's skins may be: they meet, never overlap."""
    big = 400.0
    barrel = box(L.BARREL_X[0] + 0.1, big, -50, 50, -big, big)
    receiver = box(L.RECEIVER_X[0], -0.1, -50, 50, L.FLOOR_Z - 0.1, big) + box(
        SPLIT_X + 0.2, -0.1, -50, 50, -big, L.FLOOR_Z
    )
    grip = box(-big, SPLIT_X - 0.2, -50, 50, -big, L.FLOOR_Z - 0.2)
    return {"barrel": barrel, "receiver": receiver, "grip": grip}


# -- building a style's parts -------------------------------------------------------


def _all_zones() -> Part:
    return union(zones().values())


def build_style(name: str, style: Style, fit: Fit) -> Module:
    m = Module(f"skin-{name}")
    cavity = core_cavity()
    keepout = _all_zones()
    reg = regions()
    accent_holes = union([a.holes for a in style.accents]) if style.accents else None
    for section in ("barrel", "receiver", "grip"):
        raw = (
            half_shell(style.outlines[section], FLANK[section], style.chamfer)
            & reg[section]
        )
        raw = raw - cavity
        if section in style.removals:
            raw = raw - style.removals[section]
        for side in SIDES:
            # Zones and accent holes are not symmetric: cut each half after
            # mirroring.
            shell = raw if side == "left" else mirror(raw, Plane.XZ)
            shell = shell - keepout
            if accent_holes is not None:
                shell = shell - accent_holes
            if section in style.flank_cuts:
                shell = shell - style.flank_cuts[section](side)
            a = ATTACHMENTS[(section, side)]
            part = shell + a.hook_tab() - a.skin_cuts(fit)
            part = _largest(part)
            m.add(
                Printed(
                    f"skin-{name}-{section}-{side}",
                    part,
                    UP[side],
                    "skin",
                    kind="skin",
                    perimeters=3,
                    infill=15,
                )
            )
            m.add(
                bought(
                    "m3x8",
                    a.screw_location(),
                    f"skin screw, {section} {side}",
                    "skin",
                    teardown=True,
                )
            )
    for accent in style.accents:
        m.add(
            Printed(
                f"accent-{name}-{accent.name}",
                accent.shape,
                accent.up,
                "skin",
                kind="accent",
                perimeters=3,
                infill=20,
            )
        )
        # Its pegs press into their holes through the skins.
        for section in ("barrel", "receiver", "grip"):
            for side in SIDES:
                m.fit(f"accent-{name}-{accent.name}", f"skin-{name}-{section}-{side}")
    return m


def _largest(part: Part) -> Part:
    """Keep-outs can shave slivers off a skin's edge; keep the skin."""
    solids = sorted(part.solids(), key=lambda s: s.volume, reverse=True)
    if len(solids) > 1 and solids[1].volume > 5.0:
        raise AssertionError(
            f"a skin fell apart into pieces of {[round(s.volume) for s in solids]}"
        )
    return Part(solids[0].wrapped) if len(solids) > 1 else part


def press_peg(
    start: Sequence[float], axis: Sequence[float], length: float, fit: Fit
) -> tuple[Part, Part]:
    """(peg, hole): a 3 mm peg pressed into a hole, by the interference."""
    from boresight_case.geom import cylinder

    hole_r = 1.5
    peg = cylinder(start, axis, hole_r + fit.interference, length)
    hole = cylinder(start, axis, hole_r, length + 4.0)
    return peg, hole


__all__ = ["Location", "build_style", "Style", "Accent", "grip_outline", "press_peg"]
