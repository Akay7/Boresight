"""Shared, cached builds: an assembly is modelled once per configuration and
its meshes tessellated once, however many tests look at them."""

from __future__ import annotations

from functools import cache

import manifold3d as m3
import pytest

from boresight_case.assembly import Assembly, build
from boresight_case.config import Config
from boresight_case.mesh import to_manifold


@cache
def assembly(cfg: Config, skins: bool = False) -> Assembly:
    return build(cfg, with_skins=skins)


_MESHES: dict[int, tuple[object, m3.Manifold]] = {}


def mesh_of(shape) -> m3.Manifold:
    """`shape` as a mesh, tessellated once however many configurations
    share it (modules are cached, so their shapes are the same objects)."""
    key = id(shape)
    hit = _MESHES.get(key)
    if hit is None or hit[0] is not shape:
        hit = (shape, to_manifold(shape))
        _MESHES[key] = hit
    return hit[1]


@cache
def meshes(cfg: Config, skins: bool = False) -> dict[str, m3.Manifold]:
    """Every part of the configuration as a mesh: printed parts by name,
    purchased parts by label. Leads are routes, not parts: see
    `lead_meshes`."""
    a = assembly(cfg, skins)
    out = {name: mesh_of(p.shape) for name, p in a.printed.items()}
    out.update({b.label: mesh_of(b.shape) for b in a.bought})
    return out


@cache
def lead_meshes(cfg: Config, skins: bool = False) -> dict[str, m3.Manifold]:
    """Every lead's route as a mesh, by name."""
    return {name: mesh_of(s) for name, s in assembly(cfg, skins).extras.items()}


@cache
def everything(cfg: Config, skins: bool = False) -> dict[str, m3.Manifold]:
    return {**meshes(cfg, skins), **lead_meshes(cfg, skins)}


@cache
def oriented(cfg: Config, name: str, skins: bool = False) -> m3.Manifold:
    return to_manifold(assembly(cfg, skins).printed[name].oriented())


POWERS = ("aa", "aaa", "18650", "usb")
ESP32_DRAWERS = [Config(board="esp32-cam", power=p) for p in POWERS]
PI_DRAWERS = [Config(board="pi-zero-2w", power=p) for p in POWERS]
PI_CAMERAS = [Config(board="pi-zero-2w", power="aa", camera=c) for c in ("cm2", "cm3")]
BARREL_COUNTS = [
    Config(barrels=0),
    Config(barrels=2),
    Config(board="pi-zero-2w", barrels=2),
]
FEEDBACK = [
    Config(board=b, power=p, feedback=f)
    for b in ("esp32-cam", "pi-zero-2w")
    for f, p in (("vibration", "aa"), ("solenoid", "18650"), ("lra", "usb"))
]
MECHANISM_CONFIGS = [
    Config(mechanism=m, trigger=t)
    for m in ("bolt", "button")
    for t in ("mx", "microswitch")
]


@pytest.fixture(params=ESP32_DRAWERS + PI_DRAWERS + BARREL_COUNTS, ids=lambda c: c.name)
def core_config(request) -> Config:
    """One configuration per kit, drawer and barrel count (the switch plate
    and style do not change the core)."""
    return request.param
