"""The geometry checks: bed fit, interference, overhangs, field of view and
clearances, on manifold meshes.

Each check returns a list of Problems, empty when the geometry passes. A
problem names the parts involved, so a failing test or a skin report says
exactly what to change.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import manifold3d as m3
import numpy as np

from boresight_case.geom import MAX_BRIDGE
from boresight_case.mesh import arrays, intersection_volume

# Overlap below this, in mm^3, is coincident-face noise from tessellation.
INTERFERENCE_TOLERANCE = 1.0
# A downward face more than 45 degrees from vertical is an overhang. A
# hair past 45 is allowed so that a modelled 45-degree chamfer, after
# tessellation, still passes.
OVERHANG_LIMIT_DEG = 45.0
OVERHANG_SLACK_DEG = 1.5
# Overhanging area, in mm^2, tolerated as tessellation noise per part.
OVERHANG_NOISE = 2.0
# Faces this close to the lowest point lie on the bed.
BED_TOLERANCE = 0.1


@dataclass(frozen=True)
class Problem:
    check: str
    parts: tuple[str, ...]
    detail: str

    def text(self) -> str:
        return f"{self.check}: {', '.join(self.parts)}: {self.detail}"


# -- bed fit -----------------------------------------------------------------


def bed_fit(name: str, oriented: m3.Manifold, volume: Sequence[float]) -> list[Problem]:
    """`oriented` is the part in print orientation. It must fit the volume
    (x, y on the bed, z up), allowing any rotation about z of 0 or 90."""
    lo, hi = (
        np.array(oriented.bounding_box()[:3]),
        np.array(oriented.bounding_box()[3:]),
    )
    size = hi - lo
    vx, vy, vz = volume
    fits = size[2] <= vz and (
        (size[0] <= vx and size[1] <= vy) or (size[0] <= vy and size[1] <= vx)
    )
    if fits:
        return []
    return [
        Problem(
            "bed",
            (name,),
            f"{size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm does not fit "
            f"{vx:g} x {vy:g} x {vz:g} mm",
        )
    ]


# -- interference --------------------------------------------------------------


def interference(
    parts: Mapping[str, m3.Manifold],
    allowed: Iterable[frozenset[str]] = (),
    tolerance: float = INTERFERENCE_TOLERANCE,
) -> list[Problem]:
    """Every pair of `parts` that overlaps by more than `tolerance`, except
    the pairs in `allowed` (declared press fits)."""
    allowed = set(allowed)
    names = list(parts)
    boxes = {n: np.array(parts[n].bounding_box()) for n in names}
    problems = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if frozenset((a, b)) in allowed or not _boxes_touch(boxes[a], boxes[b]):
                continue
            overlap = intersection_volume(parts[a], parts[b])
            if overlap > tolerance:
                problems.append(
                    Problem("interference", (a, b), f"overlap {overlap:.1f} mm^3")
                )
    return problems


def overlapping(
    zone: m3.Manifold,
    parts: Mapping[str, m3.Manifold],
    check: str,
    zone_name: str,
    tolerance: float = INTERFERENCE_TOLERANCE,
) -> list[Problem]:
    """Every part that enters `zone` by more than `tolerance`."""
    zb = np.array(zone.bounding_box())
    problems = []
    for name, man in parts.items():
        if not _boxes_touch(zb, np.array(man.bounding_box())):
            continue
        overlap = intersection_volume(zone, man)
        if overlap > tolerance:
            problems.append(
                Problem(check, (name, zone_name), f"enters it by {overlap:.1f} mm^3")
            )
    return problems


def _boxes_touch(a: np.ndarray, b: np.ndarray, pad: float = 0.01) -> bool:
    return bool(np.all(a[:3] <= b[3:] + pad) and np.all(b[:3] <= a[3:] + pad))


# -- clearance -----------------------------------------------------------------


def too_close(
    a_name: str,
    a: m3.Manifold,
    others: Mapping[str, m3.Manifold],
    distance: float,
    check: str,
) -> list[Problem]:
    """Every part of `others` nearer than `distance` to `a`."""
    problems = []
    for name, man in others.items():
        gap = float(a.min_gap(man, distance + 1.0))
        if gap < distance:
            problems.append(
                Problem(check, (name, a_name), f"{gap:.1f} mm away, needs {distance:g}")
            )
    return problems


# -- overhangs -----------------------------------------------------------------


@dataclass(frozen=True)
class OverhangReport:
    steep_area: float  # overhang area that is not a short bridge
    bridges: tuple[float, ...]  # the width of each accepted bridge


def analyse_overhangs(
    oriented: m3.Manifold,
    limit_deg: float = OVERHANG_LIMIT_DEG,
    max_bridge: float = MAX_BRIDGE,
) -> OverhangReport:
    """Downward faces, in print orientation, steeper than `limit_deg` from
    vertical and off the bed. A horizontal patch no wider than `max_bridge`
    across is a bridge; everything else counts toward the steep area."""
    verts, tris = arrays(oriented)
    if len(tris) == 0:
        return OverhangReport(0.0, ())
    p0, p1, p2 = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    cross = np.cross(p1 - p0, p2 - p0)
    area = np.linalg.norm(cross, axis=1) / 2
    with np.errstate(invalid="ignore", divide="ignore"):
        normal = cross / (2 * area[:, None])
    nz = normal[:, 2]
    zmin = verts[:, 2].min()
    on_bed = np.all(
        np.stack([p0[:, 2], p1[:, 2], p2[:, 2]], axis=1) < zmin + BED_TOLERANCE, axis=1
    )
    threshold = -math.sin(math.radians(limit_deg + OVERHANG_SLACK_DEG))
    over = (nz < threshold) & ~on_bed & (area > 1e-9)
    horizontal = over & (nz < -0.999)
    steep_area = float(area[over & ~horizontal].sum())
    bridges = []
    for patch in _patches(tris, np.flatnonzero(horizontal)):
        pts = verts[np.unique(tris[patch].reshape(-1))][:, :2]
        width = _min_width(pts)
        if width <= max_bridge + 1e-6:
            bridges.append(width)
        else:
            steep_area += float(area[patch].sum())
    return OverhangReport(steep_area, tuple(bridges))


def overhangs(
    name: str, oriented: m3.Manifold, noise: float = OVERHANG_NOISE
) -> list[Problem]:
    report = analyse_overhangs(oriented)
    if report.steep_area <= noise:
        return []
    return [
        Problem(
            "overhang",
            (name,),
            f"{report.steep_area:.1f} mm^2 of overhang steeper than "
            f"{OVERHANG_LIMIT_DEG:g} degrees that is not a bridge up to "
            f"{MAX_BRIDGE:g} mm",
        )
    ]


def _patches(tris: np.ndarray, selected: np.ndarray) -> list[np.ndarray]:
    """Connected groups of the `selected` triangles, by shared vertices."""
    if len(selected) == 0:
        return []
    parent = list(range(len(selected)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first: dict[int, int] = {}
    for k, t in enumerate(selected):
        for vtx in tris[t]:
            vtx = int(vtx)
            if vtx in first:
                ra, rb = find(k), find(first[vtx])
                if ra != rb:
                    parent[ra] = rb
            else:
                first[vtx] = k
    groups: dict[int, list[int]] = {}
    for k in range(len(selected)):
        groups.setdefault(find(k), []).append(int(selected[k]))
    return [np.array(g) for g in groups.values()]


def _min_width(points: np.ndarray) -> float:
    """The smallest width of a 2-D point set (rotating calipers on its hull)."""
    hull = _convex_hull(points)
    if len(hull) < 3:
        return 0.0
    best = math.inf
    for i in range(len(hull)):
        a, b = hull[i], hull[(i + 1) % len(hull)]
        edge = b - a
        length = math.hypot(*edge)
        if length < 1e-9:
            continue
        n = np.array([-edge[1], edge[0]]) / length
        proj = hull @ n
        best = min(best, float(proj.max() - proj.min()))
    return best


def _cross2(a: np.ndarray, b: np.ndarray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _convex_hull(points: np.ndarray) -> np.ndarray:
    pts = np.unique(np.round(points, 6), axis=0)
    if len(pts) < 3:
        return pts
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def half(seq: np.ndarray) -> list[np.ndarray]:
        out: list[np.ndarray] = []
        for p in seq:
            while len(out) >= 2 and _cross2(out[-1] - out[-2], p - out[-2]) <= 0:
                out.pop()
            out.append(p)
        return out

    lower, upper = half(pts), half(pts[::-1])
    return np.array(lower[:-1] + upper[:-1])
