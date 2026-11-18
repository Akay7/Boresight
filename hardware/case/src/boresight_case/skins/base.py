"""What every cover style shares: how a silhouette becomes cover parts.

The covers are held only by the gun's through-bolts. Every cover section
ends on a line of port bolts, so each port's two bolts clamp the edges of
the covers either side of it: the washer and the nut bridge the seam, and
the nut's hex pocket is split between the two right-hand covers.

    receiver: x -100 .. -6       a barrel: -6 .. 94 (moved along for each)
    grip: below the receiver, and a band up the receiver's flank to the
          grip bolt (z = -21), where it meets the receiver's covers
    muzzle ring: from the muzzle port's bolts forward, round the camera
          module's plate or the nose

A style draws, for each section, the gun's outline in side view. Each half
(left, right) is that outline extruded from just off the midplane out to
the flank, its outer edge chamfered at 45 degrees. From it come away the
core, every keep-out zone and the section's neighbours; then each bolt
position gets its hole, and on the right its nut's hex pocket. The muzzle
ring is one part, both halves joined.

Covers are printed flank down; the ring standing on its front face.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import cache

from build123d import Part, Plane, Polygon, extrude, mirror

from boresight_case import layout as L
from boresight_case.geom import NEG_X, X, Z, box, cylinder, frame, union
from boresight_case.interfaces import FLANGE, Fit, ThroughBolt
from boresight_case.joints import (
    BACKSTRAP_BOLT,
    GRIP_BOLT,
    REAR_PORT,
    RECEIVER_PORT,
    barrel_port,
)
from boresight_case.keepouts import core_envelope, section_zones
from boresight_case.model import Module, Printed
from boresight_case.vendor import M3_CLEAR

Pts = list[tuple[float, float]]
SKIN_T = FLANGE  # every cover's flank is a flange
POCKET = 2.0  # the nut's hex pocket in a right-hand cover, from its outer face
GAP_Y = 0.2  # each half stops this short of the midplane
SEAM = 0.1  # each section stops this short of a seam
SEAM_Z = L.GRIP_BOLT[1]  # the grip's covers meet the receiver's here
FLANK = {
    "barrel": L.HALF_W + SKIN_T,
    "receiver": L.HALF_W + SKIN_T,
    "grip": L.GRIP_WIDTH / 2 + SKIN_T,
    "muzzle": L.HALF_W + SKIN_T,
}
SIDES = ("left", "right")
UP = {"left": (0, -1, 0), "right": (0, 1, 0)}  # printed flank down
RECEIVER_SEAM = RECEIVER_PORT.bolt_x  # -6
BARREL_SPAN = (RECEIVER_SEAM, barrel_port(0).bolt_x)  # -6 .. 94
MUZZLE_SEAM = barrel_port(0).bolt_x  # 94, for a muzzle at x = 100


@dataclass
class Accent:
    """A separate decorative part, captured between a cover and the bone:
    it shows through a window in the cover, and a flange round it sits in
    a recess on the cover's inside."""

    name: str
    shape: Part
    holes: Part  # what it needs cut from the covers
    up: tuple[float, float, float]
    section: str


@dataclass
class Style:
    """A style's drawing: an outline per section, and what it adds."""

    outlines: dict[str, list[Pts]]  # unioned polygons, side view (x, z)
    chamfer: float
    removals: dict[str, Part] = field(default_factory=dict)  # per section, both halves
    flank_cuts: dict[str, Callable[[str], Part]] = field(default_factory=dict)
    accents: list[Accent] = field(default_factory=list)


def grip_outline(extra: float = SKIN_T, bottom: float = L.GRIP_LENGTH - 0.1) -> Pts:
    return L.grip_outline(extra, bottom)


def grip_band_x() -> tuple[float, float]:
    """The grip covers' band up the receiver's flank: its x span."""
    a = L.GRIP_DEPTH / 2 + SKIN_T
    return (L.grip_top_x(-a), L.grip_top_x(a))


def _xz(points: Pts, y: float):
    return frame((0, y, 0), X, Z) * Polygon(*points, align=None)


def _shell(face, flank: float, chamfer: float, y0: float) -> Part:
    body = extrude(face(y0), amount=flank - chamfer - y0, dir=(0, 1, 0))
    cap = extrude(face(flank - chamfer), amount=chamfer, dir=(0, 1, 0), taper=45)
    if cap.bounding_box().max.Y < flank - 0.01:
        raise AssertionError("chamfer taper went the wrong way")
    return body + cap


def half_shell(
    polys: list[Pts], flank: float, chamfer: float, y0: float = GAP_Y
) -> Part:
    """The left half's raw solid: each outline from y0 to the flank, the
    last `chamfer` of it tapering at 45 degrees. The outlines are joined
    into one face first, so a thin feature merged into its neighbour
    survives the chamfer; where that fails, each is shelled on its own."""

    def merged(y: float):
        faces = [_xz(pts, y) for pts in polys]
        out = faces[0]
        for f in faces[1:]:
            out = out + f
        return out

    try:
        return _shell(merged, flank, chamfer, y0)
    except (RuntimeError, ValueError):
        pass
    return union(
        _shell(lambda y, pts=pts: _xz(pts, y), flank, chamfer, y0) for pts in polys
    )


# -- where each section may be ---------------------------------------------------------


def regions() -> dict[str, Part]:
    """Where each section's covers may be: they meet, never overlap. The
    barrel's and the ring's in the first barrel's place."""
    big = 400.0
    bx0, bx1 = grip_band_x()
    band = box(bx0, bx1, -50, 50, -L.HALF_H - SKIN_T - 1, SEAM_Z - SEAM)
    under = box(-big, 0, -50, 50, -big, -L.HALF_H - SKIN_T - 1)
    receiver = box(
        L.RECEIVER_X[0], RECEIVER_SEAM - SEAM, -50, 50, -L.HALF_H - SKIN_T - 1, big
    ) - box(bx0 - SEAM, bx1 + SEAM, -50, 50, -big, SEAM_Z + SEAM)
    grip = (band + under) & box(-big, RECEIVER_SEAM - SEAM, -50, 50, -big, big)
    barrel = box(BARREL_SPAN[0] + SEAM, BARREL_SPAN[1] - SEAM, -50, 50, -big, big)
    muzzle = box(MUZZLE_SEAM + SEAM, big, -50, 50, -big, big)
    return {"receiver": receiver, "grip": grip, "barrel": barrel, "muzzle": muzzle}


def section_bolts(section: str) -> list[ThroughBolt]:
    """The through-bolts each section's covers take, in its own place."""
    if section == "receiver":
        return [*REAR_PORT.bolts, *RECEIVER_PORT.bolts, GRIP_BOLT]
    if section == "grip":
        return [GRIP_BOLT, BACKSTRAP_BOLT]
    if section == "barrel":
        return [*RECEIVER_PORT.bolts, *barrel_port(0).bolts]
    return list(barrel_port(0).bolts)


def section_zone_shapes(section: str) -> Part:
    """Every zone a section's covers keep out of, in its own place."""
    s = section_zones()
    from boresight_case.joints import through_bolts

    access = union(b.head_room(60) + b.nut_room(60) for b in through_bolts(1))
    if section in ("receiver", "grip"):
        return union(list(s["gun"].values()) + [access])
    if section == "barrel":
        return union(list(s["barrel"].values()) + [access])
    return union(list(s["muzzle"].values()) + [access])


def cavity(section: str) -> Part:
    """The core a section's covers wrap: every configuration's, in that
    section's place (the muzzle ring's round the nose, which reaches
    furthest forward)."""
    return core_envelope(None)


def bolt_cuts(section: str, side: str, fit: Fit, up: Sequence[float]) -> Part:
    """Each of the section's bolts: its clear hole, and on the right the
    nut's hex pocket from the outer face."""
    cuts = []
    for b in section_bolts(section):
        x, _, z = b.centre
        r = M3_CLEAR / 2 + fit.clearance / 2
        if side == "left":
            cuts.append(cylinder((x, b.half - 1, z), (0, 1, 0), r, SKIN_T + 2))
        else:
            cuts.append(cylinder((x, -b.half + 1, z), (0, -1, 0), r, SKIN_T + 2))
            cuts.append(b.nut_pocket(fit, up, POCKET))
    return union(cuts)


def _largest(part: Part, name: str) -> Part:
    """Keep-outs can shave slivers off a cover's edge; keep the cover."""
    solids = sorted(part.solids(), key=lambda s: s.volume, reverse=True)
    if len(solids) > 1 and solids[1].volume > 5.0:
        raise AssertionError(
            f"{name} fell apart into pieces of {[round(s.volume) for s in solids]}"
        )
    return Part(solids[0].wrapped) if len(solids) > 1 else part


def _accent_cuts(style: Style, section: str) -> Part | None:
    holes = [a.holes for a in style.accents if a.section == section]
    return union(holes) if holes else None


@cache
def _zones(section: str) -> Part:
    return section_zone_shapes(section)


def build_style(name: str, style: Style, fit: Fit) -> Module:
    """Every cover part of a style, each in its own section's place: the
    barrel's in the first barrel's, the ring at a muzzle of x = 100."""
    m = Module(f"skin-{name}")
    reg = regions()
    for section in ("receiver", "grip", "barrel"):
        raw = (
            half_shell(style.outlines[section], FLANK[section], style.chamfer)
            & reg[section]
        )
        raw = raw - cavity(section)
        if section == "grip":
            # Up the receiver's flank its band is flush with the receiver's
            # covers, so the grip bolt's washer and nut sit on both.
            bx0, bx1 = grip_band_x()
            raw = raw - box(bx0 - 1, bx1 + 1, FLANK["receiver"], 50, L.FLOOR_Z, 50)
        if section in style.removals:
            raw = raw - style.removals[section]
        keepout = _zones(section)
        accents = _accent_cuts(style, section)
        for side in SIDES:
            shell = raw if side == "left" else mirror(raw, Plane.XZ)
            shell = shell - keepout
            if accents is not None:
                shell = shell - accents
            if section in style.flank_cuts:
                shell = shell - style.flank_cuts[section](side)
            shell = shell - bolt_cuts(section, side, fit, UP[side])
            part_name = f"skin-{name}-{section}-{side}"
            m.add(
                Printed(
                    part_name,
                    _largest(shell, part_name),
                    UP[side],
                    "skin",
                    kind="skin",
                    perimeters=3,
                    infill=15,
                )
            )
    m.add(
        Printed(
            f"skin-{name}-muzzle",
            muzzle_ring(style, fit),
            NEG_X,
            "skin",
            kind="skin",
            perimeters=3,
            infill=20,
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
    return m


def muzzle_ring(style: Style, fit: Fit) -> Part:
    """The ring round the muzzle: both halves of the style's muzzle outline
    as one part, from the muzzle port's bolts forward."""
    raw = half_shell(style.outlines["muzzle"], FLANK["muzzle"], style.chamfer, y0=-0.01)
    raw = raw & regions()["muzzle"]
    whole = raw + mirror(raw, Plane.XZ)
    whole = whole - cavity("muzzle") - _zones("muzzle")
    for side in SIDES:
        whole = whole - bolt_cuts("muzzle", side, fit, NEG_X)
    return _largest(whole, "the muzzle ring")


def window_accent(
    name: str,
    section: str,
    side: str,
    x: tuple[float, float],
    z: tuple[float, float],
    fit: Fit,
) -> Accent:
    """An accent strip in a window through a cover's flank, its flange in a
    recess on the cover's inside, so the cover traps it against the bone."""
    sign = 1 if side == "left" else -1
    flank = FLANK[section]
    inner = flank - SKIN_T
    c = fit.clearance
    lip = 1.5
    recess = 0.8
    x0, x1 = x
    z0, z1 = z
    body = box(x0, x1, sign * inner, sign * flank, z0, z1)
    flange = box(
        x0 - lip,
        x1 + lip,
        sign * inner,
        sign * (inner + recess - c),
        z0 - lip,
        z1 + lip,
    )
    holes = box(
        x0 - c, x1 + c, sign * (inner - 0.5), sign * (flank + 0.5), z0 - c, z1 + c
    ) + box(
        x0 - lip - c,
        x1 + lip + c,
        sign * (inner - 0.5),
        sign * (inner + recess),
        z0 - lip - c,
        z1 + lip + c,
    )
    return Accent(name, body + flange, holes, (0, sign, 0), section)


def placed(module: Module, barrels: int) -> Module:
    """A style's covers on a gun of `barrels` barrels: a copy of the barrel
    covers for each barrel, the ring at the muzzle, the others where they
    are."""
    out = Module(module.name)
    dx = L.muzzle_x(barrels) - L.barrel_x(0)[1]
    for p in module.printed:
        if "-barrel-" in p.name:
            for k in range(barrels):
                name = p.name if k == 0 else f"{p.name} {k + 1}"
                out.printed.append(p.moved((k * L.BARREL_LEN, 0, 0), name))
        elif p.name.endswith("-muzzle"):
            out.printed.append(p.moved((dx, 0, 0), p.name) if dx else p)
        else:
            out.printed.append(p)
    out.bought = list(module.bought)
    out.press_fits = list(module.press_fits)
    return out


__all__ = ["build_style", "Style", "Accent", "grip_outline", "placed", "window_accent"]
