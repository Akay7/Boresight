"""Every place two parts meet, each defined once.

Each interface yields both sides of the fit, the positive feature on one
part and the negative on the other, from one set of numbers and the
printer's clearance and interference. The two halves of a fit therefore
cannot drift apart, and changing the clearance opens every fit together.

Frames follow `geom`: x forward, y left, z up. Each feature that prints
sideways takes the part's `up`, its print direction, so its holes get
45-degree roofs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from build123d import Location, Part, Plane, Rectangle, Vector, loft

from boresight_case import layout as L
from boresight_case.config import Printer
from boresight_case.geom import (
    Vec,
    box,
    cylinder,
    hex_location,
    hexagon_prism,
    oriented_box,
    prism,
    teardrop,
    unit,
    v,
)
from boresight_case.vendor import (
    M3_CLEAR,
    M3_HEAD_CBORE,
    M3_INSERT_HOLE,
    M3_INSERT_LEN,
    M3_NUT_AF,
    M3_NUT_H,
    M3_NYLOC_H,
    M3_WASHER,
)


@dataclass(frozen=True)
class Fit:
    """The printer's fit settings, as every interface reads them."""

    clearance: float = 0.25
    interference: float = 0.05
    fastener: str = "nut"

    @classmethod
    def of(cls, printer: Printer) -> Fit:
        return cls(printer.clearance, printer.interference, printer.fastener)

    @property
    def nut_af(self) -> float:
        """A nut pocket's width across flats: a press fit on the nut."""
        return M3_NUT_AF - 2 * self.interference


def _gusset_block(
    base_centre: Vector,
    out: Vector,
    side: Vector,
    height: float,
    width: float,
    length: float,
    up: Sequence[float],
) -> Part:
    """A block on a wall, protruding `height` along `out`, `width` along
    `side` and `length` along out x side. When it sticks out sideways in
    print, a 45-degree ramp under it carries its lower face back to the wall
    so it prints without support."""
    out, side = out.normalized(), side.normalized()
    u = v(up)
    down = -(u - out * u.dot(out))
    if down.length >= 0.3:
        # Square the block to the print's down direction, so the ramp under
        # it covers its whole lower face, keeping each extent on the axis
        # nearest the one asked for.
        squared = out.cross(down.normalized()).normalized()
        if abs(squared.dot(side)) < 0.7:
            width, length = length, width
        side = squared
    third = out.cross(side).normalized()
    block = oriented_box(
        base_centre + out * (height / 2), side, third, (width, length, height)
    )
    if down.length < 0.3:
        return block
    d = down.normalized()
    half = abs(d.dot(side)) * width / 2 + abs(d.dot(third)) * length / 2
    across = out.cross(d).normalized()
    span = abs(across.dot(side)) * width + abs(across.dot(third)) * length
    # prism() extrudes along d x out, which is -across.
    o = base_centre + d * half + across * (span / 2)
    ramp = prism(o, d, out, [(0, 0), (height, 0), (0, height)], span)
    return block + ramp


@dataclass(frozen=True)
class ModuleJoint:
    """A rectangular tenon on the inserting module, entering a socket in
    the receiver, held by one M3 x 12 screw through the socket's wall into a
    nut (or a heat-set insert) in a boss inside the tenon.

    `mouth` is the centre of the socket's opening, `axis` the direction the
    tenon travels in, and `opening` the socket's inside (width along `u`,
    height along axis x u). The screw enters from the host's outer face
    along `screw_dir`, `screw_at` from the mouth along the axis and
    `screw_offset` across the other in-plane direction.
    """

    name: str
    mouth: Vec
    axis: Vec
    u: Vec
    opening: tuple[float, float]
    depth: float
    screw_dir: Vec
    screw_at: float
    screw_offset: float = 0.0
    wall: float = 2.5
    host_wall: float = 2.5

    @property
    def _a(self) -> Vector:
        return unit(self.axis)

    @property
    def _u(self) -> Vector:
        return unit(self.u)

    @property
    def _h(self) -> Vector:
        return self._a.cross(self._u).normalized()

    def tenon_outer(self, fit: Fit) -> tuple[float, float]:
        w, h = self.opening
        return (w - 2 * fit.clearance, h - 2 * fit.clearance)

    def _screw_geometry(self, fit: Fit) -> tuple[Vector, Vector, Vector, float]:
        """(entry point on the host's outer face, screw direction, the
        in-plane direction it crosses, half the opening along it)."""
        d = unit(self.screw_dir)
        if abs(d.dot(self._u)) > 0.99:
            half, across = self.opening[0] / 2, self._h
        else:
            half, across = self.opening[1] / 2, self._u
        at = v(self.mouth) + self._a * self.screw_at + across * self.screw_offset
        entry = at - d * (half + self.host_wall)
        return entry, d, across, half

    def tenon(self, fit: Fit, up: Sequence[float]) -> Part:
        """The tenon: a hollow rectangular tube from the mouth, plus the boss
        that holds the nut."""
        ow, oh = self.tenon_outer(fit)
        iw, ih = ow - 2 * self.wall, oh - 2 * self.wall
        centre = v(self.mouth) + self._a * (self.depth / 2)
        outer = oriented_box(centre, self._u, self._h, (ow, oh, self.depth))
        inner = oriented_box(centre, self._u, self._h, (iw, ih, self.depth + 1))
        entry, d, across, half = self._screw_geometry(fit)
        boss_base = entry + d * (self.host_wall + fit.clearance + self.wall)
        boss = _gusset_block(boss_base, d, across, 5.0, 8.0, 8.0, up)
        return (outer - inner) + boss + self._root(fit)

    def _root(self, fit: Fit) -> Part:
        """A collar behind the mouth that fuses the tenon, inset by the
        clearance, to its own module's walls. Its inside flares at 45
        degrees from the tenon's bore to the full opening, so it prints
        without support in any orientation along the axis."""
        w, h = self.opening
        ow, oh = self.tenon_outer(fit)
        iw, ih = ow - 2 * self.wall, oh - 2 * self.wall
        step = (w - iw) / 2
        straight = 2.0
        a, u, hd = self._a, self._u, self._h
        m = v(self.mouth)
        length = straight + step
        collar = oriented_box(m - a * (length / 2), u, hd, (w + 0.5, h + 0.5, length))
        bore = oriented_box(m - a * (straight / 2), u, hd, (iw, ih, straight + 0.02))
        near = Plane(origin=m - a * straight, x_dir=u, z_dir=-a) * Rectangle(iw, ih)
        far = Plane(origin=m - a * (length + 0.01), x_dir=u, z_dir=-a) * Rectangle(
            w + 0.02, h + 0.02
        )
        flare = loft([near, far])
        return collar - bore - flare

    def tube(self, fit: Fit) -> Part:
        """The tenon's tube and its root collar, without the screw's boss."""
        ow, oh = self.tenon_outer(fit)
        iw, ih = ow - 2 * self.wall, oh - 2 * self.wall
        centre = v(self.mouth) + self._a * (self.depth / 2)
        outer = oriented_box(centre, self._u, self._h, (ow, oh, self.depth))
        inner = oriented_box(centre, self._u, self._h, (iw, ih, self.depth + 1))
        return (outer - inner) + self._root(fit)

    def tenon_cuts(self, fit: Fit, up: Sequence[float]) -> Part:
        entry, d, _, _ = self._screw_geometry(fit)
        tenon_face = entry + d * (self.host_wall + fit.clearance)
        hole = teardrop(tenon_face - d * 0.5, d, M3_CLEAR / 2, 12.0, up)
        if fit.fastener == "insert":
            pocket = cylinder(
                tenon_face - d * 0.01, d, M3_INSERT_HOLE / 2, M3_INSERT_LEN
            )
        else:
            # The nut sits against the tenon wall's inside face; the pocket
            # opens into the tenon so the nut goes in from inside.
            nut_start = tenon_face + d * self.wall
            pocket = hexagon_prism(nut_start + d * 2.5, d, fit.nut_af, 5.0, up)
        return hole + pocket

    def host_cuts(self, fit: Fit, up: Sequence[float]) -> Part:
        entry, d, _, _ = self._screw_geometry(fit)
        return teardrop(entry - d * 0.5, d, M3_CLEAR / 2, self.host_wall + 1.0, up)

    def screw_location(self, fit: Fit) -> Location:
        """Where the M3 x 12 envelope goes: head on the host's outer face."""
        entry, d, _, _ = self._screw_geometry(fit)
        return Location(Plane(origin=entry, z_dir=-d))

    def nut_location(self, fit: Fit, up: Sequence[float]) -> Location:
        entry, d, _, _ = self._screw_geometry(fit)
        c = entry + d * (self.host_wall + fit.clearance + self.wall + M3_NUT_H / 2)
        return hex_location(c, d, up)

    def insert_location(self, fit: Fit) -> Location:
        entry, d, _, _ = self._screw_geometry(fit)
        top = entry + d * (self.host_wall + fit.clearance)
        return Location(Plane(origin=top, z_dir=-d))

    def head_clearance(self) -> Part:
        """The screw head's space outside the host: skins keep out of it."""
        entry, d, _, _ = self._screw_geometry(Fit())
        return cylinder(entry, -d, M3_HEAD_CBORE / 2 + 0.3, 3.4)


@dataclass(frozen=True)
class ScrewFix:
    """One M3 screw clamping parts together into a nut (or a heat-set
    insert). `entry` is where the head's underside sits, `direction` the way
    the screw travels, `clamp` the depth of everything it passes through
    before the nut. The nut part holds the nut in a pocket that opens on
    the far side, so the screw pulls the nut onto the pocket's floor."""

    name: str
    entry: Vec
    direction: Vec
    clamp: float
    length: float = 12.0

    @property
    def _d(self) -> Vector:
        return unit(self.direction)

    def clear_hole(self, up: Sequence[float], depth: float | None = None) -> Part:
        d = self._d
        depth = self.clamp + 0.5 if depth is None else depth
        return teardrop(v(self.entry) - d * 0.5, d, M3_CLEAR / 2, depth + 0.5, up)

    def head_room(self, depth: float = 3.4) -> Part:
        d = self._d
        return cylinder(v(self.entry) + d * 0.01, -d, M3_HEAD_CBORE / 2, depth)

    def nut_cuts(self, fit: Fit, up: Sequence[float], open_len: float = 5.0) -> Part:
        d = self._d
        seat = v(self.entry) + d * self.clamp
        hole = teardrop(seat - d * 0.5, d, M3_CLEAR / 2, open_len + 4.0, up)
        if fit.fastener == "insert":
            # The insert goes in from the screw's side: the clamped part's
            # hole is then its only guide, so it reaches back through it.
            return hole + cylinder(
                seat - d * 0.01, d, M3_INSERT_HOLE / 2, M3_INSERT_LEN
            )
        return hole + hexagon_prism(
            seat + d * (open_len / 2), d, fit.nut_af, open_len, up
        )

    def boss(self, up: Sequence[float], size: float = 8.0, height: float = 5.0) -> Part:
        """A boss around the nut, standing on the face at the nut's seat."""
        d = self._d
        side = _perpendicular_to(d)
        return _gusset_block(
            v(self.entry) + d * self.clamp, d, side, height, size, size, up
        )

    def screw_location(self) -> Location:
        return Location(Plane(origin=v(self.entry), z_dir=-self._d))

    def nut_location(self, fit: Fit, up: Sequence[float]) -> Location:
        c = v(self.entry) + self._d * (self.clamp + M3_NUT_H / 2)
        return hex_location(c, self._d, up)

    def insert_location(self) -> Location:
        return Location(
            Plane(origin=v(self.entry) + self._d * self.clamp, z_dir=-self._d)
        )


def _perpendicular_to(d: Vector) -> Vector:
    trial = Vector(0, 0, 1) if abs(d.Z) < 0.9 else Vector(1, 0, 0)
    return (trial - d * trial.dot(d)).normalized()


# Through-bolts ----------------------------------------------------------------

FLANGE = 3.0  # a cover's flange, or a spacer collar, under a head or a nut
LAP = 1.5  # each cover's layer where two covers lap at a bolt
COLLAR_OD = 9.0


@dataclass(frozen=True)
class ThroughBolt:
    """An M3 x 50 straight through the gun along y: its head (on a washer)
    on the left cover's flange, a nylon-insert nut in a hex pocket in the
    right cover. Between the bone walls a crush tube, part of whatever
    fills the port, takes the clamp load.

    `centre` is where the bolt crosses the midplane, `half` half the width
    of the bones it crosses (18 for the body, 18.6 for the grip)."""

    name: str
    centre: Vec
    half: float = 18.0
    length: float = 50.0

    @property
    def head_y(self) -> float:
        """The flange's outer face under the head's washer."""
        return self.half + FLANGE

    @property
    def nut_y(self) -> float:
        """The right flange's outer face, where the nut seats."""
        return -(self.half + FLANGE)

    def _at(self, y: float) -> Vector:
        x, _, z = self.centre
        return Vector(x, y, z)

    def hole(self, y0: float, y1: float, up: Sequence[float]) -> Part:
        """The clear hole from y0 to y1 (a teardrop when it lies sideways)."""
        lo, hi = sorted((y0, y1))
        return teardrop(
            self._at(hi + 0.01), (0, -1, 0), M3_CLEAR / 2, hi - lo + 0.02, up
        )

    def crush_tube(self, y0: float, y1: float, up: Sequence[float]) -> Part:
        """The crush tube between y0 and y1: solid, pointed on top in print,
        with the bolt's hole through it."""
        lo, hi = sorted((y0, y1))
        # A solid bar sideways in print: its underside comes to the point.
        down = tuple(-c for c in unit(up))
        tube = teardrop(self._at(hi), (0, -1, 0), L.CRUSH_R, hi - lo, down)
        return tube - self.hole(lo - 1, hi + 1, up)

    def washer_location(self) -> Location:
        return Location(Plane(origin=self._at(self.head_y), z_dir=(0, 1, 0)))

    def bolt_location(self) -> Location:
        """Head's underside on the washer, shank toward -y."""
        return Location(
            Plane(origin=self._at(self.head_y + M3_WASHER[1]), z_dir=(0, 1, 0))
        )

    def nut_location(self, up: Sequence[float], pocket: float = 0.0) -> Location:
        """The nut on the right flange's outer face, or sunk `pocket` into a
        cover's hex pocket."""
        c = self._at(self.nut_y + pocket - M3_NYLOC_H / 2)
        return hex_location(c, (0, 1, 0), up)

    def nut_pocket(self, fit: Fit, up: Sequence[float], depth: float) -> Part:
        """The nut's hex pocket in the right cover, from its outer face
        `depth` in: the nut goes in from outside and bears on its floor."""
        c = self._at(self.nut_y + depth / 2 - 0.01)
        return hexagon_prism(c, (0, 1, 0), fit.nut_af, depth + 0.02, up)

    def sweep(self, extra: float = 0.5) -> Part:
        """The bolt's whole length, grown by `extra`: what it may not touch."""
        top = self.head_y + M3_WASHER[1]
        return cylinder(self._at(top), (0, -1, 0), 1.5 + extra, self.length)

    def head_room(self, depth: float = 4.0) -> Part:
        """The space a hex key and the head need outside the left flange."""
        return cylinder(
            self._at(self.head_y), (0, 1, 0), M3_HEAD_CBORE / 2 + 0.3, depth
        )

    def nut_room(self, depth: float = 8.0) -> Part:
        """The space outside the right flange that the nut and the bolt's
        tail take."""
        return cylinder(
            self._at(self.nut_y), (0, -1, 0), M3_HEAD_CBORE / 2 + 0.3, depth
        )

    def collar(self, side: int, fit: Fit) -> Part:
        """A 3 mm spacer collar, standing in for a cover's flange on a bench
        build: on the left (+1) or right (-1) flank."""
        y0 = side * self.half
        y1 = side * (self.half + FLANGE)
        lo, hi = sorted((y0, y1))
        ring = cylinder(self._at(lo), (0, 1, 0), COLLAR_OD / 2, hi - lo)
        return ring - cylinder(
            self._at(lo - 1), (0, 1, 0), M3_CLEAR / 2 + fit.clearance / 2, hi - lo + 2
        )


def _crush_and_holes(
    bolts: Sequence[ThroughBolt], y: float, up: Sequence[float]
) -> tuple[Part, Part]:
    """(the crush tubes across +-y, the holes through everything)."""
    from boresight_case.geom import union

    tubes = union(b.crush_tube(-y, y, up) for b in bolts)
    holes = union(b.hole(-30, 30, up) for b in bolts)
    return tubes, holes


@dataclass(frozen=True)
class Port:
    """A port: the 31 x 45 opening at a bone's end, 12 mm deep, keyed by a
    rib under its top wall, with two through-bolts 6 mm in from its mouth.

    `mouth` is the x of the opening; `facing` +1 when it opens forward (its
    bone lies behind it), -1 when it opens backward. A tenon goes in along
    -facing."""

    name: str
    mouth: float
    facing: int

    @property
    def bolt_x(self) -> float:
        return self.mouth - self.facing * L.PORT_BOLT_AT

    @property
    def bolts(self) -> tuple[ThroughBolt, ThroughBolt]:
        return tuple(
            ThroughBolt(
                f"{self.name} bolt {'upper' if z > 0 else 'lower'}", (self.bolt_x, 0, z)
            )
            for z in L.PORT_BOLT_Z
        )

    @property
    def zone(self) -> tuple[float, float]:
        """The port's span along x, inside its bone."""
        return tuple(sorted((self.mouth, self.mouth - self.facing * L.PORT_DEPTH)))

    # the host's side ---------------------------------------------------------

    def rib(self) -> Part:
        """The key rib under the host's top wall, through the port's depth."""
        kw, kd = L.KEY_RIB
        x0, x1 = self.zone
        # Its front end, toward the mouth, is where a tenon first meets it.
        return box(x0, x1, -kw / 2, kw / 2, L.IN_HALF_H - kd, L.IN_HALF_H + 0.01)

    def host_cuts(self, up: Sequence[float]) -> Part:
        from boresight_case.geom import union

        return union(b.hole(-L.HALF_W - 1, L.HALF_W + 1, up) for b in self.bolts)

    # the filler's side ---------------------------------------------------------

    def tenon(self, fit: Fit, up: Sequence[float], root: bool = True) -> Part:
        """The standard tenon: a keyed tube in the port, its two crush tubes
        and the bolts' holes, and (with `root`) a collar behind the mouth
        that fuses it to its own module's walls."""
        c = fit.clearance
        ow, oh = L.IN_W - 2 * c, L.IN_H - 2 * c
        t = L.WALL
        x0, x1 = self.zone
        outer = box(x0, x1, -ow / 2, ow / 2, -oh / 2, oh / 2)
        inner = box(x0 - 1, x1 + 1, -ow / 2 + t, ow / 2 - t, -oh / 2 + t, oh / 2 - t)
        kw, kd = L.KEY_RIB
        slot = box(
            x0 - 1, x1 + 1, -kw / 2 - c, kw / 2 + c, oh / 2 - t - 0.5, oh / 2 + 1
        )
        tubes, holes = _crush_and_holes(self.bolts, ow / 2 - t + 0.01, up)
        shape = (outer - inner - slot) + tubes
        if root:
            shape = shape + self._root(fit)
        return shape - holes

    def tenon_cuts(self, up: Sequence[float]) -> Part:
        """What a module that carries its own tenon must cut from itself."""
        _, holes = _crush_and_holes(self.bolts, L.IN_HALF_W, up)
        return holes

    def _root(self, fit: Fit) -> Part:
        """A collar on the filler's side of the mouth that fuses the tenon,
        inset by the clearance, to its own module's walls. Its inside flares
        at 45 degrees from the tenon's bore to the full opening, so it prints
        without support either way along the axis."""
        c = fit.clearance
        w, h = L.IN_W, L.IN_H
        iw, ih = w - 2 * c - 2 * L.WALL, h - 2 * c - 2 * L.WALL
        step = (w - iw) / 2
        straight = 2.0
        a = Vector(-self.facing, 0, 0)  # into the host
        u, hd = Vector(0, 1, 0), Vector(0, 0, 1)
        m = Vector(self.mouth, 0, 0)
        length = straight + step
        collar = oriented_box(m - a * (length / 2), u, hd, (w + 0.5, h + 0.5, length))
        bore = oriented_box(m - a * (straight / 2), u, hd, (iw, ih, straight + 0.02))
        near = Plane(origin=m - a * straight, x_dir=u, z_dir=-a) * Rectangle(iw, ih)
        far = Plane(origin=m - a * (length + 0.01), x_dir=u, z_dir=-a) * Rectangle(
            w + 0.02, h + 0.02
        )
        return collar - bore - loft([near, far])


# Rails ------------------------------------------------------------------------


def rails(x0: float, x1: float, side: int, fit: Fit, up: Sequence[float]) -> Part:
    """The C-channels on one inner wall (left +1, right -1) from x0 to x1,
    holding a carrier plate's top and bottom edges. The rails' end that
    faces down in print slopes back to the wall at 45 degrees."""
    from boresight_case.geom import union

    c = fit.clearance
    inner, _ = L.plate_y(side)
    wall = side * L.IN_HALF_W
    face = inner - side * c  # the lip's back, a clearance off the plate
    lip_front = face - side * 1.0
    down = -1 if unit(up).X > 0 else 1  # which x end faces the bed
    parts = []
    for edge, outward in ((L.RAIL_Z[1], 1), (L.RAIL_Z[0], -1)):
        back = edge + outward * c
        top = back + outward * 2.0
        z0, z1 = sorted((back, top))
        parts.append(_rail(x0, x1, wall, lip_front, z0, z1, down))
        zl0, zl1 = sorted((edge - outward * 1.5, top))
        parts.append(_rail(x0, x1, face, lip_front, zl0, zl1, down))
    return union(parts)


def _rail(
    x0: float, x1: float, y_wall: float, y_far: float, z0: float, z1: float, down: int
) -> Part:
    """A bar along x from the wall out to y_far, its bed-side end sloping at
    45 degrees back to the wall."""
    depth = abs(y_far - y_wall)
    if down < 0:  # the -x end faces the bed
        pts = [(x0, y_wall), (x1, y_wall), (x1, y_far), (x0 + depth, y_far)]
    else:
        pts = [(x0, y_wall), (x1, y_wall), (x1 - depth, y_far), (x0, y_far)]
    shape = prism((0, 0, z0), (1, 0, 0), (0, 1, 0), pts, z1 - z0)
    return shape


def carrier_plate(x0: float, x1: float, side: int) -> Part:
    """A carrier's plate on the left (+1) or right (-1) rails."""
    inner, outer = L.plate_y(side)
    return box(x0, x1, inner, outer, *L.RAIL_Z)


# Pegs, slots and keys --------------------------------------------------------


@dataclass(frozen=True)
class Peg:
    """A printed peg through a board's mounting hole, from a standoff."""

    base: Vec
    axis: Vec
    hole_d: float
    length: float
    standoff_d: float = 5.0
    standoff_h: float = 0.0

    def peg(self, fit: Fit) -> Part:
        a = unit(self.axis)
        tip = cylinder(
            v(self.base) + a * self.standoff_h,
            a,
            self.hole_d / 2 - fit.clearance,
            self.length,
        )
        if self.standoff_h <= 0:
            return tip
        return tip + cylinder(self.base, a, self.standoff_d / 2, self.standoff_h)

    def hole(self) -> Part:
        """The board's hole, for checking the fit against the peg."""
        a = unit(self.axis)
        return cylinder(
            v(self.base) + a * self.standoff_h, a, self.hole_d / 2, self.length
        )


@dataclass(frozen=True)
class SlideFit:
    """A rectangular part sliding into a rectangular pocket: a bulkhead in
    the barrel, a drawer in the grip bay, a switch plate in its seat.

    The pocket is `size` (along u, along v), the slider `size` minus the
    clearance each side. `key` adds a rib to the pocket at +v and a matching
    groove to the slider, so the slider only goes in one way round.
    """

    centre: Vec
    axis: Vec
    u: Vec
    size: tuple[float, float]
    length: float
    key: tuple[float, float] | None = None  # rib (width along u, depth along v)

    @property
    def _a(self) -> Vector:
        return unit(self.axis)

    @property
    def _u(self) -> Vector:
        return unit(self.u)

    @property
    def _v(self) -> Vector:
        return self._a.cross(self._u).normalized()

    def pocket(self) -> Part:
        c = v(self.centre) + self._a * (self.length / 2)
        p = oriented_box(c, self._u, self._v, (*self.size, self.length))
        if self.key:
            p = p - self.rib()
        return p

    def rib(self) -> Part:
        assert self.key is not None
        kw, kd = self.key
        # Its inner face exactly kd in from the pocket wall; the extra 0.02
        # reaches only past the outside, so the cut leaves no sliver.
        c = (
            v(self.centre)
            + self._a * (self.length / 2)
            + self._v * (self.size[1] / 2 - kd / 2 + 0.01)
        )
        return oriented_box(c, self._u, self._v, (kw, kd + 0.02, self.length + 0.02))

    def slider(self, fit: Fit) -> Part:
        """The slider's outline at full length; the part trims it to shape."""
        c = v(self.centre) + self._a * (self.length / 2)
        w, h = self.size
        s = oriented_box(
            c,
            self._u,
            self._v,
            (w - 2 * fit.clearance, h - 2 * fit.clearance, self.length),
        )
        if self.key:
            kw, kd = self.key
            g = c + self._v * (h / 2 - kd / 2)
            s = s - oriented_box(
                g,
                self._u,
                self._v,
                (kw + 2 * fit.clearance, kd + 2 * fit.clearance, self.length + 1),
            )
        return s

    def reversed_slider(self, fit: Fit) -> Part:
        """The slider turned 180 degrees about the axis: the wrong way round."""
        c = v(self.centre) + self._a * (self.length / 2)
        return self.slider(fit).rotate(_axis(c, self._a), 180)


def _axis(origin: Vector, direction: Vector):
    from build123d import Axis

    return Axis(origin, direction)


def chamfer_wedge(
    origin: Sequence[float],
    a: Sequence[float],
    b: Sequence[float],
    size: float,
    length: float,
) -> Part:
    """A 45-degree triangular prism filling the inside corner between
    directions `a` and `b` at `origin`, `length` along a x b."""
    return prism(origin, a, b, [(0, 0), (size, 0), (0, size)], length)
