"""What a module is made of: printed parts and the purchased parts they hold.

Every shape is in the gun's coordinates. A printed part also knows `up`,
the direction that points away from the bed when it is printed; turning it
so that `up` is +z and setting it on z = 0 gives the exported part.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from build123d import Location, Part, Plane, Vector

from boresight_case.geom import Vec, unit
from boresight_case.vendor import VENDOR, VendorPart

PETG = "PETG"
PLA_OR_PETG = "PLA or PETG"


@dataclass
class Printed:
    """One printed part where it sits in the gun. `name` is unique in the
    gun; `part` is the file it prints from, shared by every copy (the two
    barrels of a long gun, the spacer collars)."""

    name: str
    shape: Part
    up: Vec
    module: str
    kind: str = "core"  # core, skin, accent
    material: str = PLA_OR_PETG
    perimeters: int = 3
    infill: int = 25
    part: str = ""

    def __post_init__(self) -> None:
        if not self.part:
            self.part = self.name

    def moved(self, by: Sequence[float], name: str) -> Printed:
        """A copy of this part, moved along by `by`, under another name."""
        return Printed(
            name,
            Location(tuple(by)) * self.shape,
            self.up,
            self.module,
            self.kind,
            self.material,
            self.perimeters,
            self.infill,
            self.part,
        )

    def print_location(self) -> Location:
        """The rigid motion from gun coordinates to the print bed."""
        up = unit(self.up)
        x = Vector(1, 0, 0) if abs(up.X) < 0.9 else Vector(0, 1, 0)
        x = (x - up * x.dot(up)).normalized()
        turn = Location(Plane(origin=(0, 0, 0), x_dir=x, z_dir=up)).inverse()
        bb = (turn * self.shape).bounding_box()
        centre = Vector((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, bb.min.Z)
        return Location(-centre) * turn

    def oriented(self) -> Part:
        return self.print_location() * self.shape


@dataclass
class Bought:
    key: str
    shape: Part
    label: str
    module: str
    # Undone in a full teardown (a bolt that separates bones, a module or a
    # cover).
    teardown: bool = False

    def moved(self, by: Sequence[float], label: str) -> Bought:
        return Bought(
            self.key,
            Location(tuple(by)) * self.shape,
            label,
            self.module,
            self.teardown,
        )

    @property
    def vendor(self) -> VendorPart:
        return VENDOR[self.key]


def bought(
    key: str, where: Location, label: str, module: str, teardown: bool = False
) -> Bought:
    return Bought(key, where * VENDOR[key].build(), label, module, teardown)


@dataclass
class Module:
    name: str
    printed: list[Printed] = field(default_factory=list)
    bought: list[Bought] = field(default_factory=list)
    # Overlaps that are the design: a nut pressed into its pocket, a
    # plug on its pins. Pairs of part names or purchased labels.
    press_fits: list[tuple[str, str]] = field(default_factory=list)

    def add(self, *items: Printed | Bought) -> Module:
        for item in items:
            (self.printed if isinstance(item, Printed) else self.bought).append(item)
        return self

    def fit(self, a: str, b: str) -> None:
        self.press_fits.append((a, b))

    def moved(self, by: Sequence[float], rename) -> Module:
        """A copy of the module moved along by `by`; `rename` maps each part
        name or label to its new one."""
        out = Module(self.name)
        out.printed = [p.moved(by, rename(p.name)) for p in self.printed]
        out.bought = [b.moved(by, rename(b.label)) for b in self.bought]
        out.press_fits = [(rename(a), rename(b)) for a, b in self.press_fits]
        return out


def merge(modules: Iterable[Module]) -> Module:
    out = Module("gun")
    for m in modules:
        out.printed += m.printed
        out.bought += m.bought
        out.press_fits += m.press_fits
    return out


def translate(shape: Part, by: Sequence[float]) -> Part:
    return Location(tuple(by)) * shape
