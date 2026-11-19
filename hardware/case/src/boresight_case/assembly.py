"""A whole gun for one configuration: every bone, module, drawer and cover
placed, with the bolts that hold them and the leads between them, ready
to check and export."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cache

from build123d import Location, Part, Pos, Sphere

from boresight_case import catalog
from boresight_case import layout as L
from boresight_case.config import Config
from boresight_case.geom import cylinder, union
from boresight_case.interfaces import Fit, ThroughBolt
from boresight_case.joints import through_bolts
from boresight_case.model import Bought, Module, Printed, bought, merge
from boresight_case.parts import carriers, drawers, kits
from boresight_case.parts.barrel import barrel
from boresight_case.parts.grip import contacts, grip, thumbscrew_nut
from boresight_case.parts.rear_cap import rear_cap
from boresight_case.parts.receiver import receiver
from boresight_case.parts.trigger import LEAD_R as TRIGGER_LEAD_R
from boresight_case.parts.trigger import trigger_lead_path, trigger_module

LEAD_R = 1.5  # a lead's bundle, for the checks


@dataclass
class Assembly:
    config: Config
    printed: dict[str, Printed]
    bought: list[Bought]
    press_fits: set[frozenset[str]]
    bolts: list[ThroughBolt] = field(default_factory=list)
    # Lead paths, by lead name: polylines through the gun.
    leads: dict[str, list[tuple[float, float, float]]] = field(default_factory=dict)
    extras: dict[str, Part] = field(default_factory=dict)

    def printed_names(self) -> list[str]:
        return list(self.printed)

    def bought_by_label(self) -> dict[str, Bought]:
        return {b.label: b for b in self.bought}

    def part_counts(self) -> Counter:
        return Counter(p.part for p in self.printed.values())


def barrel_name(k: int) -> str:
    return "barrel" if k == 0 else f"barrel {k + 1}"


def _moved(m: Module, dx: float, rename=None) -> Module:
    if not dx and rename is None:
        return m
    return m.moved((dx, 0, 0), rename or (lambda n: n))


def _runs(fit: Fit, cfg: Config) -> list[Module]:
    """The hub and what fills the rest of the receiver's two runs."""
    out = [carriers.hub(fit)]
    left = Module("spacers")
    x = L.HUB_X[1]
    for length, name in catalog.SPACER_LEFT[cfg.buttons]:
        if name == "button-panel":
            out.append(carriers.button_panel(fit))
        else:
            left.add(carriers.spacer(length, +1, x, fit))
        x += length
    x = L.RECEIVER_RUN[0]
    for length, _ in catalog.SPACER_RIGHT:
        left.add(carriers.spacer(length, -1, x, fit))
        x += length
    if cfg.feedback == "none":
        length, _ = catalog.NO_FEEDBACK
        left.add(carriers.spacer(length, -1, x, fit))
    else:
        out.append(carriers.feedback_carrier(fit, cfg.feedback))
    out.append(left)
    return out


def _kit(fit: Fit, cfg: Config) -> Module:
    """The board kit at the gun's muzzle."""
    dx = L.muzzle_x(cfg.barrels) - kits.MUZZLE
    if cfg.board == "esp32-cam":
        return _moved(kits.esp32_kit(fit), dx)
    last = barrel_name(cfg.barrels - 1)
    return _moved(
        kits.pi_kit(fit, cfg.camera), dx, lambda n: last if n == "barrel" else n
    )


def _bolts(fit: Fit, cfg: Config, covers: bool) -> tuple[Module, list[ThroughBolt]]:
    """Every through-bolt: its washer, the bolt and its lock nut, and on a
    bench build the spacer collars that stand in for the covers' flanges."""
    from boresight_case.skins.base import POCKET

    m = Module("bolts")
    bolts = through_bolts(cfg.barrels)
    for b in bolts:
        m.add(bought("m3-washer", b.washer_location(), f"washer, {b.name}", "bolts"))
        m.add(bought("m3x50", b.bolt_location(), b.name, "bolts", teardown=True))
        nut = b.nut_location((0, 0, 1), POCKET if covers else 0.0)
        m.add(bought("m3-nyloc", nut, f"nut, {b.name}", "bolts"))
        m.fit(b.name, f"nut, {b.name}")  # its nylon ring grips the thread
        if not covers:
            for side, label in ((+1, "left"), (-1, "right")):
                name = f"collar, {b.name}, {label}"
                m.add(
                    Printed(
                        name,
                        b.collar(side, fit),
                        (0, side, 0),
                        "bolts",
                        perimeters=3,
                        infill=100,
                        part=catalog.COLLAR,
                    )
                )
    return m, bolts


def _fasteners(fit: Fit, cfg: Config) -> Module:
    """The battery lead's contacts in the grip, and the thumbscrew's nut."""
    m = Module("fasteners")
    m.add(*contacts())
    m.add(thumbscrew_nut(fit))
    m.fit("grip", "nut, thumbscrew")
    m.fit("thumbscrew", "nut, thumbscrew")
    return m


# -- the leads -----------------------------------------------------------------------

LANE = (-3.0, -18.0)  # y, z of the leads' way along the floor, under the crush tubes
LANE_RECEIVER_Z = -15.5  # over the grip socket's front rib


def _floor(x: float, z: float = LANE[1]) -> tuple[float, float, float]:
    return (x, LANE[0], z)


def lead_paths(cfg: Config) -> dict[str, list[tuple[float, float, float]]]:
    """Each lead's way from its module to the hub, as a polyline."""
    out: dict[str, list[tuple[float, float, float]]] = {}
    mouth = {s.lead: carriers.socket_mouth(s) for s in carriers.SOCKETS}
    # The battery: from the grip's contacts up the bore to the hub's underside.
    out["battery lead"] = [
        tuple(L.grip_point(L.BAY_CEILING_S - L.CEILING_T - 1.0, 0, 0)),
        tuple(L.grip_point(12.0, -2.0, 1.5)),
        mouth["battery"],
    ]
    out["trigger lead"] = trigger_lead_path(cfg.mechanism) + [mouth["trigger"]]
    if cfg.feedback != "none":
        x0, z0 = carriers.FB_LEAD_AT
        out["feedback lead"] = [(x0, -5.0, z0), (-62.0, -9.0, 2.0), mouth["feedback"]]
    if cfg.buttons:
        out["buttons lead"] = [(-41.0, 3.0, 9.0), (-70.0, -9.0, 3.0), mouth["buttons"]]
    muzzle = L.muzzle_x(cfg.barrels)
    along = [
        _floor(-50.0, LANE_RECEIVER_Z),
        _floor(-16.0, LANE_RECEIVER_Z),
        _floor(-10.0),
    ]
    if cfg.board == "esp32-cam":
        # In the nose's sleeve the only room is between the crush tubes, so
        # the lead rises before the muzzle port.
        plug = (muzzle + 3.0, -L.IN_HALF_W + 4.0, 12.5)
        rise = [
            _floor(muzzle - 24.0),
            (muzzle - 16.0, LANE[0], 0.0),
            (muzzle + 3.0, -8.0, 0.0),
        ]
        if cfg.barrels == 0:
            rise = [(muzzle - 16.0, LANE[0], 0.0), (muzzle + 3.0, -8.0, 0.0)]
            along = along[:1]
        out["board lead"] = (
            [mouth["esp32-cam"], (-56.0, -9.0, -8.0)] + along + rise + [plug]
        )
    else:
        base = muzzle - L.BARREL_LEN
        header = (base + 28.0, -10.0, L.PI_Z0 + 25.2)
        out["Pi signal lead"] = (
            [mouth["pi signal"], (-56.0, -9.0, 4.0)]
            + along
            + [_floor(base + 30.0), (base + 30.0, -10.0, -10.0), header]
        )
        pwr = (base + L.PI_X0 + 54.0 - 8.0, 3.0, -16.5)
        out["Pi power lead"] = (
            [mouth["pi power"], (-56.0, -9.0, -2.0)]
            + along
            + [_floor(base + 40.0), pwr]
        )
    return out


def path_length(points: Sequence[Sequence[float]]) -> float:
    return sum(
        sum((b - a) ** 2 for a, b in zip(p, q, strict=True)) ** 0.5
        for p, q in zip(points, points[1:], strict=False)
    )


def cable_solid(points: Sequence[Sequence[float]], radius: float = LEAD_R) -> Part:
    pieces = []
    for p, q in zip(points, points[1:], strict=False):
        d = [b - a for a, b in zip(p, q, strict=True)]
        length = sum(c * c for c in d) ** 0.5
        if length > 1e-6:
            pieces.append(cylinder(p, d, radius, length))
    pieces += [Pos(*p) * Sphere(radius) for p in points[1:-1]]
    return union(pieces)


# -- the gun ---------------------------------------------------------------------


def core_modules(fit: Fit, cfg: Config) -> list[Module]:
    mods = [receiver(fit), rear_cap(fit), grip(fit)]
    for k in range(cfg.barrels):
        name = barrel_name(k)
        mods.append(_moved(barrel(fit), k * L.BARREL_LEN, lambda n, name=name: name))
    mods.append(trigger_module(fit, cfg.mechanism, cfg.trigger))
    mods.append(drawers.drawer(fit, cfg.power))
    mods += _runs(fit, cfg)
    mods.append(_kit(fit, cfg))
    mods.append(_fasteners(fit, cfg))
    return mods


@cache
def build(cfg: Config, with_skins: bool = True) -> Assembly:
    fit = Fit.of(cfg.printer)
    mods = core_modules(fit, cfg)
    bolt_mod, bolts = _bolts(fit, cfg, with_skins)
    mods.append(bolt_mod)
    if with_skins:
        from boresight_case.skins import skin_module

        skins = skin_module(cfg)
        mods.append(skins)
        # Each lock nut is pressed into the hex pocket in the right-hand
        # covers it clamps.
        for b in bolts:
            for p in skins.printed:
                if p.name.endswith("-muzzle") or "-right" in p.name:
                    bolt_mod.fit(p.name, f"nut, {b.name}")
    gun = merge(mods)
    printed: dict[str, Printed] = {}
    for p in gun.printed:
        if p.name in printed:
            raise AssertionError(f"two printed parts are named {p.name!r}")
        printed[p.name] = p
    expected = catalog.part_counts(cfg, with_skins)
    built = Counter(p.part for p in printed.values())
    if built != expected:
        raise AssertionError(f"built {dict(built)}, catalogue says {dict(expected)}")
    fits = {frozenset(p) for p in gun.press_fits}
    leads = lead_paths(cfg)
    return Assembly(
        config=cfg,
        printed=printed,
        bought=gun.bought,
        press_fits=fits,
        bolts=bolts,
        leads=leads,
        extras={
            name: cable_solid(pts, TRIGGER_LEAD_R if name == "trigger lead" else LEAD_R)
            for name, pts in leads.items()
        },
    )


__all__ = ["Assembly", "build", "Location"]
