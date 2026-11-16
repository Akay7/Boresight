"""A whole gun for one configuration: every module, kit and drawer placed,
with the screws that join them, ready to check and export."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cache

from build123d import Part, Pos, Sphere

from boresight_case import catalog
from boresight_case import layout as L
from boresight_case.config import Config
from boresight_case.geom import cylinder, union
from boresight_case.interfaces import Fit
from boresight_case.joints import MODULE_JOINTS
from boresight_case.model import Bought, Module, Printed, bought, merge
from boresight_case.parts import drawers, kits
from boresight_case.parts.barrel import barrel
from boresight_case.parts.grip import contacts, grip
from boresight_case.parts.rear_cap import led, power_parts, rear_cap
from boresight_case.parts.receiver import receiver
from boresight_case.parts.trigger import trigger_module

CABLE_R = 2.0


@dataclass
class Assembly:
    config: Config
    printed: dict[str, Printed]
    bought: list[Bought]
    press_fits: set[frozenset[str]]
    extras: dict[str, Part] = field(default_factory=dict)

    def printed_names(self) -> list[str]:
        return list(self.printed)

    def bought_by_label(self) -> dict[str, Bought]:
        return {b.label: b for b in self.bought}


def core_modules(fit: Fit, cfg: Config) -> list[Module]:
    mods = [
        receiver(fit),
        barrel(fit),
        rear_cap(fit),
        grip(fit),
        trigger_module(fit, cfg.mechanism, cfg.trigger),
    ]
    mods.append(
        kits.esp32_kit(fit)
        if cfg.board == "esp32-cam"
        else kits.pi_kit(fit, cfg.camera)
    )
    mods.append(drawers.drawer(fit, cfg.power))
    return mods


def _joint_screws(fit: Fit) -> Module:
    m = Module("joints")
    for j in MODULE_JOINTS:
        m.add(
            bought(
                "m3x12",
                j.screw_location(fit),
                f"{j.name} screw",
                "receiver",
                teardown=True,
            )
        )
    return m


def _power(cfg: Config) -> Module:
    """The battery path: contacts, switch and regulator, for every ESP32-CAM
    build. The Pi takes its power from its own USB cable."""
    m = Module("power")
    if cfg.board == "esp32-cam":
        m.add(*contacts(), *power_parts())
    else:
        m.add(led())
    return m


def pi_cable_path() -> list[tuple[float, float, float]]:
    """The Pi's USB cable, from its 90-degree plug, over the grip socket's
    front rib, down the grip's bore and through the ceiling's hole into the
    tether drawer, and out of the base."""
    plug_x = L.PI_X0 + 41.4 - 7.5
    head = [
        (plug_x, 7.5, -16.3),
        (plug_x - 2.0, 7.0, -14.6),
        (-62.0, 2.0, -14.4),
        (-71.0, 0.0, -15.5),
        (-72.0, 3.0, -30.0),
        tuple(L.grip_point(12.0, 6.0, 6.0)),
        tuple(L.grip_point(17.0, 12.0, 8.0)),
    ]
    return head + drawers.cable_path()


def cable_solid(points: Sequence[Sequence[float]], radius: float = CABLE_R) -> Part:
    pieces = []
    for p, q in zip(points, points[1:], strict=False):
        d = [b - a for a, b in zip(p, q, strict=True)]
        length = sum(c * c for c in d) ** 0.5
        pieces.append(cylinder(p, d, radius, length))
    pieces += [Pos(*p) * Sphere(radius) for p in points[1:-1]]
    return union(pieces)


@cache
def build(cfg: Config, with_skins: bool = True) -> Assembly:
    fit = Fit.of(cfg.printer)
    mods = core_modules(fit, cfg) + [_joint_screws(fit), _power(cfg)]
    if with_skins:
        from boresight_case.skins import skin_module

        mods.append(skin_module(cfg))
    gun = merge(mods)
    printed = {p.name: p for p in gun.printed}
    expected = (
        catalog.part_names(cfg)
        if with_skins
        else [
            n for n in catalog.part_names(cfg) if not n.startswith(("skin-", "accent-"))
        ]
    )
    if sorted(printed) != sorted(expected):
        raise AssertionError(
            f"built {sorted(printed)}, catalogue says {sorted(expected)}"
        )
    extras: dict[str, Part] = {}
    fits = {frozenset(p) for p in gun.press_fits}
    if cfg.board == "pi-zero-2w":
        extras["usb cable"] = cable_solid(pi_cable_path())
        fits.add(frozenset(("USB plug", "usb cable")))  # the cable leaves its plug
    return Assembly(
        config=cfg,
        printed={n: printed[n] for n in expected},
        bought=gun.bought,
        press_fits=fits,
        extras=extras,
    )
