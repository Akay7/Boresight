"""The skins: keep-outs, both styles across every configuration, attachment,
and never touching a functional part (tasks 9.1 to 9.4)."""

from functools import cache

import pytest
from conftest import assembly, meshes, oriented

from boresight_case import checks
from boresight_case.config import Config, shipped_configurations
from boresight_case.geom import cylinder
from boresight_case.interfaces import SKIN_T, Fit
from boresight_case.joints import ATTACHMENTS
from boresight_case.keepouts import trigger_zone, zones
from boresight_case.mesh import intersection_volume, to_manifold
from boresight_case.skins import _skins
from boresight_case.styles import STYLE_PARAMS, STYLES

ALL = shipped_configurations()
CORE_CONFIGS = [
    Config(),
    Config(board="pi-zero-2w", power="usb"),
    Config(mechanism="bolt", trigger="microswitch"),
    Config(mechanism="button"),
    Config(board="pi-zero-2w", power="usb", mechanism="button", trigger="microswitch"),
]
# Parts that move through their zone: what the zone is for.
ZONE_EXEMPT = {
    "rear cap and bulkhead removal": (
        "rear-cap",
        "bulkhead-esp32-cam",
        "bulkhead-pi-camera",
    ),
    "trigger": (
        "trigger-lever-filament",
        "trigger-lever-bolt",
        "button-plunger",
        "button-cap",
    ),
}


@cache
def zone_meshes():
    return {n: to_manifold(z) for n, z in zones().items()}


def _skin_names(cfg):
    return [
        n
        for n, p in assembly(cfg, True).printed.items()
        if p.kind in ("skin", "accent")
    ]


def test_every_zone_is_non_empty():
    for name, z in zones().items():
        assert z.volume > 100, name


@pytest.mark.parametrize("cfg", CORE_CONFIGS, ids=lambda c: c.name)
def test_core_parts_stay_out_of_the_zones(cfg):
    a = assembly(cfg)
    m = meshes(cfg)
    printed = {n: m[n] for n in a.printed}
    zones_here = dict(zone_meshes())
    # Another mechanism's travel is that mechanism's concern; skins keep out
    # of them all.
    zones_here["trigger"] = to_manifold(trigger_zone(cfg.mechanism))
    for zone, zm in zones_here.items():
        if zone.startswith("view ") and zone != f"view {cfg.camera}":
            continue  # another kit's camera: its view is that kit's concern
        hits = {p.parts[0] for p in checks.overlapping(zm, printed, "zone", zone)}
        assert hits <= set(ZONE_EXEMPT.get(zone, ())), (zone, hits)


@pytest.mark.parametrize("style", STYLES)
def test_skins_print_without_support_and_fit_the_bed(style):
    cfg = Config(style=style)
    for name in _skin_names(cfg):
        part = oriented(cfg, name, True)
        assert checks.overhangs(name, part) == []
        assert checks.bed_fit(name, part, cfg.printer.volume) == []


@pytest.mark.parametrize("cfg", ALL, ids=lambda c: c.name)
def test_skins_fit_every_configuration(cfg):
    """One skin set per style fits every kit, drawer and switch: no overlap
    with any part, and nothing in a keep-out zone."""
    a = assembly(cfg, True)
    m = meshes(cfg, True)
    skins = _skin_names(cfg)
    problems = [
        p
        for p in checks.interference(m, a.press_fits)
        if p.parts[0] in skins or p.parts[1] in skins
    ]
    assert problems == [], "\n".join(p.text() for p in problems)
    for zone, zm in zone_meshes().items():
        assert checks.overlapping(zm, {n: m[n] for n in skins}, "keep-out", zone) == []


@pytest.mark.parametrize("style", STYLES)
def test_each_screw_hole_is_on_its_attachment_point(style):
    cfg = Config(style=style)
    m = meshes(cfg, True)
    for (section, side), a in ATTACHMENTS.items():
        skin = m[f"skin-{style}-{section}-{side}"]
        face, n = a.screw_axis()
        bore = to_manifold(cylinder(face - n * 0.5, n, 1.6, SKIN_T + 1.0))
        ring = to_manifold(
            cylinder(face, n, 4.5, 1.0) - cylinder(face - n, n, 3.2, 3.0)
        )
        assert intersection_volume(bore, skin) < 0.05, (section, side)
        assert intersection_volume(ring, skin) > 5.0, (section, side)


@pytest.mark.parametrize("cfg", CORE_CONFIGS, ids=lambda c: c.name)
@pytest.mark.parametrize("style", STYLES)
def test_no_skin_touches_a_functional_part(cfg, style):
    """Skins rest on the core's outside only, never on a board, camera,
    bulkhead, cell, the cassette or a wire: a skin swap moves none of them."""
    cfg = Config(
        board=cfg.board,
        power=cfg.power,
        mechanism=cfg.mechanism,
        trigger=cfg.trigger,
        style=style,
    )
    a = assembly(cfg, True)
    m = meshes(cfg, True)
    functional = {b.label for b in a.bought if b.vendor.functional}
    functional |= {
        n
        for n in a.printed
        if n.startswith(
            ("bulkhead", "sled", "trigger-", "button-", "switch-plate", "drawer-")
        )
    }
    functional |= set(a.extras)
    for skin in _skin_names(cfg):
        for f in functional:
            gap = m[skin].min_gap(m[f], 0.2)
            assert gap > 0.05, (skin, f, gap)


def _range_ends():
    for style, params in STYLE_PARAMS.items():
        for p in params:
            if p.minimum is not None:
                for end in (p.minimum, p.maximum):
                    yield style, p.name, end


@pytest.mark.parametrize("style, name, value", list(_range_ends()))
def test_both_ends_of_every_parameter_pass(style, name, value):
    cfg = Config(style=style, style_params={name: value})
    module = _skins(style, cfg.style_params, Fit())
    core = meshes(Config())
    core_printed = {n: core[n] for n in assembly(Config()).printed}
    for part in module.printed:
        o = to_manifold(part.oriented())
        assert checks.overhangs(part.name, o) == [], part.name
        assert checks.bed_fit(part.name, o, cfg.printer.volume) == [], part.name
        mm = to_manifold(part.shape)
        for zone, zm in zone_meshes().items():
            assert checks.overlapping(zm, {part.name: mm}, "keep-out", zone) == []
        assert checks.overlapping(mm, core_printed, "interference", part.name) == []


def test_accents_press_into_their_holes():
    cfg = Config(style="blaster")
    m = meshes(cfg, True)
    accents = [n for n in m if n.startswith("accent-")]
    assert len(accents) == 3
    skins = [n for n in _skin_names(cfg) if n.startswith("skin-")]
    for acc in accents:
        overlap = sum(intersection_volume(m[acc], m[s]) for s in skins)
        # The pegs' press fit, and no more.
        assert 0 < overlap < 15, (acc, overlap)


def test_restyling_replaces_only_skin_parts():
    a = assembly(Config(style="minimal"), True)
    b = assembly(Config(style="blaster"), True)
    core_a = {n: p.shape.volume for n, p in a.printed.items() if p.kind == "core"}
    core_b = {n: p.shape.volume for n, p in b.printed.items() if p.kind == "core"}
    assert core_a == core_b
