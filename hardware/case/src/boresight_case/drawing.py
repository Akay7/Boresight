"""The exploded view: every part pulled out along the way it goes in, drawn
as a hidden-line projection, each printed part labelled."""

from __future__ import annotations

from html import escape

from build123d import Compound, Location, Vector

from boresight_case import layout as L
from boresight_case.assembly import Assembly

VIEW_FROM = Vector(300, -420, 260)
SCALE = 2.0
CURVE_STEPS = 12

# How far each module moves out, along the way it comes out of the gun.
_D, _F = L.GRIP_D, L.GRIP_F
OFFSETS = {
    "barrel": Vector(70, 0, 0),
    "camera": Vector(160, 0, 0),
    "nose": Vector(160, 0, 0),
    "rear-cap": Vector(-60, 0, 0),
    "sled": Vector(70, 0, 110),
    "pi-retainer": Vector(70, 0, -110),
    "clamp": Vector(70, 0, -80),
    "hub": Vector(-30, 0, 90),
    "buttons": Vector(10, 0, 90),
    "feedback": Vector(-10, 0, -60),
    "spacer": Vector(-30, 0, 140),
    "grip": _D * 45,
    "drawer": _D * 140,
    "trigger": Vector(30, 0, -80),
}


def offset_for(module: str, name: str = "") -> Vector:
    if name.startswith(("skin-", "accent-")):
        side = 1 if "left" in name else -1 if "right" in name else 0
        base = Vector(0, 70 * side, 0)
        if name.startswith("accent-"):
            base = base + Vector(0, 25 * side, 0)
        if "-barrel-" in name:
            return base + OFFSETS["barrel"]
        if "-grip-" in name:
            return base + OFFSETS["grip"]
        if name.endswith("-muzzle"):
            return base + Vector(130, 0, 0)
        return base
    if module.startswith("drawer"):
        return OFFSETS["drawer"]
    return OFFSETS.get(module, Vector())


def drawn(a: Assembly) -> dict:
    """The parts the drawing shows: every printed part but the spacer
    collars, which are too small to label."""
    return {n: p for n, p in a.printed.items() if p.part != "spacer-collar"}


def _edge_points(edge) -> list[tuple[float, float]]:
    steps = 1 if edge.geom_type.name == "LINE" else CURVE_STEPS
    pts = [edge.position_at(t / steps) for t in range(steps + 1)]
    return [(p.X, p.Y) for p in pts]


def exploded_svg(a: Assembly) -> str:
    """The drawing, as SVG text."""
    moved = {
        name: Location(offset_for(p.module, name)) * p.shape
        for name, p in drawn(a).items()
    }
    whole = Compound(children=list(moved.values()))
    centre = whole.bounding_box().center()
    eye = centre + VIEW_FROM
    visible, _ = whole.project_to_viewport(
        tuple(eye), viewport_up=(0, 0, 1), look_at=tuple(centre)
    )
    polylines = [_edge_points(e) for e in visible.edges()]
    labels = []
    for name, shape in moved.items():
        c = shape.bounding_box().center()
        v, _ = Compound(children=[_marker(c)]).project_to_viewport(
            tuple(eye), viewport_up=(0, 0, 1), look_at=tuple(centre)
        )
        bb = Compound(children=list(v)).bounding_box()
        labels.append((name, (bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2))
    xs = [x for pl in polylines for x, _ in pl] + [x for _, x, _ in labels]
    ys = [y for pl in polylines for _, y in pl] + [y for _, _, y in labels]
    pad = 20
    x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    w, h = (x1 - x0) * SCALE, (y1 - y0) * SCALE

    def tx(x: float, y: float) -> str:
        return f"{(x - x0) * SCALE:.2f},{(y1 - y) * SCALE:.2f}"

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
        f'viewBox="0 0 {w:.0f} {h:.0f}">',
        f"<title>Boresight case, exploded: {escape(a.config.name)}</title>",
        '<rect width="100%" height="100%" fill="white"/>',
        '<g fill="none" stroke="black" stroke-width="0.6" stroke-linecap="round">',
    ]
    out += [
        f'<polyline points="{" ".join(tx(x, y) for x, y in pl)}"/>' for pl in polylines
    ]
    out += ["</g>", '<g font-family="sans-serif" font-size="11" fill="#1a5fb4">']
    for name, x, y in labels:
        out.append(
            f'<text x="{(x - x0) * SCALE:.1f}" y="{(y1 - y) * SCALE:.1f}" '
            f'text-anchor="middle">{escape(name)}</text>'
        )
    out += ["</g>", "</svg>"]
    return "\n".join(out) + "\n"


def _marker(at: Vector):
    from build123d import Box

    return Location(at) * Box(0.5, 0.5, 0.5)
