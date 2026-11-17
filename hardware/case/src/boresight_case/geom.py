"""Small geometry helpers shared by every part.

Coordinates are the gun's: x forward along the camera axis, y to the
gun's left, z up, in millimetres. The camera axis is the x axis.

Several helpers take `up`, the direction that points away from the print
bed when the part is printed. Horizontal holes and openings then get a
45-degree roof toward it, so they print without support.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from build123d import (
    Axis,
    Box,
    Circle,
    Cylinder,
    Location,
    Part,
    Plane,
    Polygon,
    Pos,
    Vector,
    extrude,
)

Vec = tuple[float, float, float]
X: Vec = (1.0, 0.0, 0.0)
Y: Vec = (0.0, 1.0, 0.0)
Z: Vec = (0.0, 0.0, 1.0)
NEG_X: Vec = (-1.0, 0.0, 0.0)
NEG_Y: Vec = (0.0, -1.0, 0.0)
NEG_Z: Vec = (0.0, 0.0, -1.0)

# The longest unsupported span a part may bridge (case-fabrication spec).
MAX_BRIDGE = 10.0


def v(p: Sequence[float]) -> Vector:
    return Vector(*p)


def unit(p: Sequence[float]) -> Vector:
    return Vector(*p).normalized()


def frame(
    origin: Sequence[float], x_dir: Sequence[float], y_dir: Sequence[float]
) -> Plane:
    """A plane whose local x and y are `x_dir` and `y_dir` (made orthogonal)."""
    x = unit(x_dir)
    y = unit(y_dir)
    z = x.cross(y).normalized()
    return Plane(origin=v(origin), x_dir=x, z_dir=z)


def box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> Part:
    """An axis-aligned box between two corners."""
    lo = (min(x0, x1), min(y0, y1), min(z0, z1))
    hi = (max(x0, x1), max(y0, y1), max(z0, z1))
    size = [h - lo_ for lo_, h in zip(lo, hi, strict=True)]
    centre = [(lo_ + h) / 2 for lo_, h in zip(lo, hi, strict=True)]
    return Pos(*centre) * Box(*size)


def centred_box(centre: Sequence[float], size: Sequence[float]) -> Part:
    return Pos(*centre) * Box(*size)


def oriented_box(
    centre: Sequence[float],
    x_dir: Sequence[float],
    y_dir: Sequence[float],
    size: Sequence[float],
) -> Part:
    """A box of `size` along (x_dir, y_dir, x_dir x y_dir), centred."""
    return Location(frame(centre, x_dir, y_dir)) * Box(*size)


def cylinder(
    start: Sequence[float], axis: Sequence[float], radius: float, length: float
) -> Part:
    """A cylinder from `start` along `axis` for `length`."""
    a = unit(axis)
    centre = v(start) + a * (length / 2)
    return Location(Plane(origin=centre, z_dir=a)) * Cylinder(radius, length)


def _perpendicular_up(axis: Vector, up: Sequence[float]) -> Vector | None:
    u = v(up)
    perp = u - axis * u.dot(axis)
    if perp.length < 1e-6:
        return None
    return perp.normalized()


def teardrop(
    start: Sequence[float],
    axis: Sequence[float],
    radius: float,
    length: float,
    up: Sequence[float] = Z,
) -> Part:
    """A round hole that prints without support: its top, toward `up`,
    rises to a 45-degree point. A hole along `up` is a plain cylinder."""
    a = unit(axis)
    top = _perpendicular_up(a, up)
    if top is None:
        return cylinder(start, axis, radius, length)
    side = top.cross(a).normalized()
    pl = frame(v(start) + a * (length / 2), side, top)
    s = radius / math.sqrt(2)
    profile = Circle(radius) + Polygon(
        (-s, s), (0, radius * math.sqrt(2)), (s, s), (0, 0), align=None
    )
    return extrude(pl * profile, amount=length / 2, both=True)


def hexagon_prism(
    centre: Sequence[float],
    axis: Sequence[float],
    across_flats: float,
    length: float,
    up: Sequence[float] = Z,
) -> Part:
    """A hex pocket, centred on `centre`, with a flat toward `up` so that a
    horizontal pocket's roof is a short bridge and its sides are 30 degrees
    from vertical."""
    a = unit(axis)
    top = _perpendicular_up(a, up) or _any_perpendicular(a)
    side = top.cross(a).normalized()
    pl = frame(centre, side, top)
    r = across_flats / math.sqrt(3)
    pts = [
        (r * math.cos(math.radians(k * 60)), r * math.sin(math.radians(k * 60)))
        for k in range(6)
    ]
    return extrude(pl * Polygon(*pts, align=None), amount=length / 2, both=True)


def hex_location(
    centre: Sequence[float], axis: Sequence[float], up: Sequence[float] = Z
) -> Location:
    """Where a nut envelope (`hexagon_prism` about +z, built with up=z) goes
    to sit square in a `hexagon_prism` pocket built with this axis and up."""
    a = unit(axis)
    top = _perpendicular_up(a, up) or _any_perpendicular(a)
    return Location(Plane(origin=v(centre), x_dir=top, z_dir=a))


def _any_perpendicular(a: Vector) -> Vector:
    trial = Vector(0, 0, 1) if abs(a.Z) < 0.9 else Vector(1, 0, 0)
    return (trial - a * trial.dot(a)).normalized()


def opening(
    centre: Sequence[float],
    normal: Sequence[float],
    across: float,
    along_up: float,
    depth: float,
    up: Sequence[float] = Z,
    across_dir: Sequence[float] | None = None,
) -> Part:
    """A rectangular cut through a wall with normal `normal`.

    `across` is the opening's width perpendicular to `up` (or along
    `across_dir`), `along_up` its height toward `up`. When the wall stands
    vertical in print and the opening is wider than a bridge may be, its top
    becomes a 45-degree gable so it prints without support. The gable adds
    height above `along_up`.
    """
    n = unit(normal)
    top = _perpendicular_up(n, up)
    if top is None:
        # The wall lies flat in print: the opening is a hole through a floor.
        side = unit(across_dir) if across_dir is not None else _any_perpendicular(n)
        top = n.cross(side).normalized()
        pl = frame(centre, side, top)
        return extrude(
            pl * Polygon(*_rect(across, along_up), align=None),
            amount=depth / 2,
            both=True,
        )
    side = top.cross(n).normalized()
    pl = frame(centre, side, top)
    pts = _rect(across, along_up)
    if across > MAX_BRIDGE:
        h = along_up / 2
        pts = [
            (-across / 2, -h),
            (across / 2, -h),
            (across / 2, h),
            (0, h + across / 2),
            (-across / 2, h),
        ]
    return extrude(pl * Polygon(*pts, align=None), amount=depth / 2, both=True)


def _rect(w: float, h: float) -> list[tuple[float, float]]:
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def prism(
    origin: Sequence[float],
    x_dir: Sequence[float],
    y_dir: Sequence[float],
    points: Iterable[tuple[float, float]],
    depth: float,
    both: bool = False,
) -> Part:
    """A polygon in the plane (x_dir, y_dir) through `origin`, extruded along
    x_dir x y_dir by `depth` (or `depth` each way when `both`)."""
    pl = frame(origin, x_dir, y_dir)
    # Explicit direction: a face's own normal follows its winding, so a
    # clockwise polygon would otherwise extrude the other way.
    return extrude(
        pl * Polygon(*points, align=None), amount=depth, dir=pl.z_dir, both=both
    )


def side_profile(points: Iterable[tuple[float, float]], y0: float, y1: float) -> Part:
    """A profile drawn in the gun's side view (x, z), extruded across y0..y1."""
    pts = list(points)
    lo, hi = min(y0, y1), max(y0, y1)
    # frame((0, hi, 0), X, Z): local x = gun x, local y = gun z, normal -y.
    return prism((0, hi, 0), X, Z, pts, hi - lo)


def union(parts: Iterable[Part]) -> Part:
    parts = list(parts)
    out = parts[0]
    for p in parts[1:]:
        out = out + p
    return out


def axis_line(start: Sequence[float], direction: Sequence[float]) -> Axis:
    return Axis(v(start), unit(direction))
