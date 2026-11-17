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

from boresight_case.config import Printer
from boresight_case.geom import (
    Vec,
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


# Skin attachment ------------------------------------------------------------

SKIN_T = 3.2  # skin flank thickness
SKIN_CBORE_DEPTH = 2.0  # leaves 1.2 mm under the screw head
HOOK_STEM = (4.0, 6.0)  # along the slide, across it
HOOK_LIP = 1.6  # the 45-degree wedge's size
NUT_BOSS = 4.5  # boss depth inside the core wall


@dataclass(frozen=True)
class AttachmentPoint:
    """Where a skin part attaches: one M3 x 8 screw through the skin into a
    nut in the core, and at the other end a hook through a slot in the core
    wall. The skin is laid on with its hook in the slot, slid along `slide`
    until the hook's 45-degree wedge is behind the wall, and screwed down.

    `normal` is the core flank's outward normal; `screw` and `hook` are on
    the flank's outer face, `hook` at the stem's centre once engaged.
    """

    name: str
    normal: Vec
    screw: Vec
    hook: Vec
    slide: Vec
    wall: float = 2.5
    stem: tuple[float, float] = HOOK_STEM
    # The nut boss inside the wall: along the slide, across it.
    boss: tuple[float, float] = (9.0, 9.0)
    # The wall is backed by solid material (a rib): cut room for the wedge
    # to pass behind it as well.
    backed: bool = False
    # The hook's wall, when it is not the screw's flank (the grip's hooks go
    # into its front wall).
    hook_normal: Vec | None = None

    @property
    def _n(self) -> Vector:
        return unit(self.normal)

    @property
    def _s(self) -> Vector:
        return unit(self.slide)

    @property
    def _hn(self) -> Vector:
        return unit(self.hook_normal) if self.hook_normal else self._n

    @property
    def _t(self) -> Vector:
        return self._hn.cross(self._s).normalized()

    # core side
    def core_boss(self, up: Sequence[float]) -> Part:
        n = self._n
        base = v(self.screw) - n * self.wall
        return _gusset_block(base, -n, self._s, NUT_BOSS, *self.boss, up)

    def core_cuts(self, fit: Fit, up: Sequence[float]) -> Part:
        n = self._n
        face = v(self.screw)
        hole = teardrop(
            face + n * 0.5, -n, M3_CLEAR / 2, self.wall + NUT_BOSS + 1.0, up
        )
        if fit.fastener == "insert":
            pocket = cylinder(face + n * 0.01, -n, M3_INSERT_HOLE / 2, M3_INSERT_LEN)
        else:
            # Opens toward the inside; the screw pulls the nut onto the wall.
            pocket = hexagon_prism(
                face - n * (self.wall + NUT_BOSS / 2 + 0.5),
                n,
                fit.nut_af,
                NUT_BOSS + 1.0,
                up,
            )
        return hole + pocket + self.slot(fit, up)

    def slot(self, fit: Fit, up: Sequence[float]) -> Part:
        """The hook's slot through the wall: long enough for the wedge to
        pass, then the skin slides it home. A backed wall also gets a pocket
        behind it, for the wedge to travel in and seat against the wall."""
        s, t, n = self._s, self._t, self._hn
        stem_s, stem_t = self.stem
        c = fit.clearance
        s0 = -stem_s / 2 - HOOK_LIP - 2 * c
        s1 = stem_s / 2 + c
        width = stem_t + 2 * c

        def cut(a0: float, a1: float, n0: float, n1: float) -> Part:
            centre = v(self.hook) + s * ((a0 + a1) / 2) + n * ((n0 + n1) / 2)
            return oriented_box(centre, s, t, (a1 - a0, width, n1 - n0))

        through = cut(s0, s1, -self.wall - 0.5, 0.5)
        if not self.backed:
            return through
        pocket = cut(
            s0, stem_s / 2 + HOOK_LIP + c, -self.wall - HOOK_LIP - c, -self.wall
        )
        return through + pocket

    def screw_location(self) -> Location:
        """M3 x 8: head on the skin's counterbore floor."""
        head = v(self.screw) + self._n * (SKIN_T - SKIN_CBORE_DEPTH)
        return Location(Plane(origin=head, z_dir=self._n))

    def nut_location(self, up: Sequence[float]) -> Location:
        c = v(self.screw) - self._n * (self.wall + M3_NUT_H / 2)
        return hex_location(c, self._n, up)

    def insert_location(self) -> Location:
        return Location(Plane(origin=v(self.screw), z_dir=self._n))

    # skin side
    def hook_tab(self) -> Part:
        """The skin's hook: a stem through the wall and a 45-degree wedge
        that catches the slot's far edge from inside."""
        s, t, n = self._s, self._t, self._hn
        stem_s, stem_t = self.stem
        depth = self.wall + HOOK_LIP
        stem_c = v(self.hook) - n * (depth / 2)
        stem = oriented_box(stem_c, s, t, (stem_s, stem_t, depth))
        # The wedge, drawn in the (s, n) plane at the stem's inner end.
        o = v(self.hook) + s * (stem_s / 2) - n * depth - t * (stem_t / 2)
        pts = [(0, 0), (HOOK_LIP, 0), (0, HOOK_LIP)]
        wedge = prism(o, s, n, pts, stem_t)
        if s.cross(n).dot(t) < 0:
            wedge = prism(o + t * stem_t, s, n, pts, stem_t)
        return stem + wedge

    def skin_cuts(self, fit: Fit) -> Part:
        n = self._n
        face = v(self.screw)
        hole = cylinder(face - n * 0.5, n, M3_CLEAR / 2 + fit.clearance / 2, SKIN_T + 1)
        cbore = cylinder(
            face + n * (SKIN_T - SKIN_CBORE_DEPTH), n, M3_HEAD_CBORE / 2, SKIN_T
        )
        return hole + cbore

    def screw_axis(self) -> tuple[Vector, Vector]:
        return v(self.screw), self._n


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
