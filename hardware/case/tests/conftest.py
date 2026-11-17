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
    purchased parts by label, cables by name."""
    a = assembly(cfg, skins)
    out = {name: mesh_of(p.shape) for name, p in a.printed.items()}
    out.update({b.label: mesh_of(b.shape) for b in a.bought})
    out.update({name: mesh_of(s) for name, s in a.extras.items()})
    return out


@cache
def oriented(cfg: Config, name: str, skins: bool = False) -> m3.Manifold:
    return to_manifold(assembly(cfg, skins).printed[name].oriented())


ESP32_DRAWERS = [
    Config(board="esp32-cam", power=p) for p in ("aa", "aaa", "18650", "usb")
]
PI_CAMERAS = [Config(board="pi-zero-2w", power="usb", camera=c) for c in ("cm2", "cm3")]
TRIGGERS = [Config(trigger="mx"), Config(trigger="microswitch")]
MECHANISM_CONFIGS = [
    Config(mechanism=m, trigger=t)
    for m in ("filament", "bolt", "button")
    for t in ("mx", "microswitch")
]


@pytest.fixture(params=ESP32_DRAWERS + PI_CAMERAS, ids=lambda c: c.name)
def core_config(request) -> Config:
    """One configuration per kit and drawer (the switch plate and style do
    not change the core)."""
    return request.param
