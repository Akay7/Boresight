"""The covers: held only by the bolts, out of every keep-out, on every
configuration (tasks 13.1, 13.2, 13.4)."""

from functools import cache

import pytest
from conftest import assembly, everything, meshes, oriented

from boresight_case import checks
from boresight_case.config import Config, shipped_configurations
from boresight_case.interfaces import FLANGE, Fit
from boresight_case.joints import through_bolts
from boresight_case.keepouts import trigger_zone, zones
from boresight_case.mesh import intersection_volume, to_manifold
from boresight_case.skins import _skins
from boresight_case.skins.base import POCKET
from boresight_case.styles import STYLE_PARAMS, STYLES

ALL = shipped_configurations()
CORE_CONFIGS = [
    Config(),
    Config(board="pi-zero-2w", power="18650", buttons=True),
    Config(mechanism="button", trigger="microswitch"),
    Config(barrels=2, feedback="solenoid"),
    Config(barrels=0),
]
# Parts that move through their zone, or fill it: what the zone is for.
ZONE_EXEMPT = {
    "rear cap removal": ("rear-cap",),
    # Its 45-degree lead-in starts on the last bone's end.
    "camera and nose removal": (
        "camera-pi",
        "nose-esp32-cam",
        "nose-sleeve",
        "receiver",
        "barrel",
        "barrel 2",
    ),
    "trigger": ("trigger-blade", "button-plunger"),
    "drawer and thumbscrew": ("drawer-aa", "drawer-aaa", "drawer-18650", "drawer-usb"),
    "window and plugs": ("cable-clamp",),
    "nose top": ("nose-esp32-cam",),
}


@cache
def zone_meshes(cfg: Config):
    return {n: to_manifold(z) for n, z in zones(cfg).items()}


def _skin_names(cfg):
    return [
        n
        for n, p in assembly(cfg, True).printed.items()
        if p.kind in ("skin", "accent")
    ]


def test_every_zone_is_non_empty():
    for name, z in zones(Config()).items():
        assert z.volume > 100, name


@pytest.mark.parametrize("cfg", CORE_CONFIGS, ids=lambda c: c.name)
def test_core_parts_stay_out_of_the_zones(cfg):
    a = assembly(cfg)
    m = meshes(cfg)
    printed = {n: m[n] for n in a.printed}
    zones_here = dict(zone_meshes(cfg))
    zones_here["trigger"] = to_manifold(trigger_zone(cfg.mechanism))
    for zone, zm in zones_here.items():
        if zone.startswith("view ") and zone != f"view {cfg.camera}":
            continue  # another kit's camera: its view is that kit's concern
        if zone == "nose top" and cfg.board != "esp32-cam":
            continue
        hits = {p.parts[0] for p in checks.overlapping(zm, printed, "zone", zone)}
        assert hits <= set(ZONE_EXEMPT.get(zone, ())), (zone, hits)


@pytest.mark.parametrize("style", STYLES)
def test_covers_print_without_support_and_fit_the_bed(style):
    cfg = Config(style=style)
    for name in _skin_names(cfg):
        part = oriented(cfg, name, True)
        assert checks.overhangs(name, part) == [], name
        assert checks.bed_fit(name, part, cfg.printer.volume) == [], name


@pytest.mark.parametrize("cfg", ALL, ids=lambda c: c.name)
def test_covers_fit_every_configuration(cfg):
    """One set of covers per style fits every kit, drawer, mechanism, barrel
    count, feedback device and the buttons: no overlap with any part, and
    nothing in a keep-out zone."""
    a = assembly(cfg, True)
    m = meshes(cfg, True)
    skins = set(_skin_names(cfg))
    problems = [
        p
        for p in checks.interference(m, a.press_fits)
        if p.parts[0] in skins or p.parts[1] in skins
    ]
    assert problems == [], "\n".join(p.text() for p in problems)
    for zone, zm in zone_meshes(cfg).items():
        hits = checks.overlapping(zm, {n: m[n] for n in skins}, "keep-out", zone)
        assert hits == [], [h.text() for h in hits]


@pytest.mark.parametrize(
    "cfg", [Config(), Config(barrels=2), Config(barrels=0)], ids=lambda c: c.name
)
def test_each_bolt_clamps_covers_on_both_sides(cfg):
    """Every through-bolt passes a clear hole in a left cover's flange and a
    right cover's, its nut in a hex pocket."""
    m = meshes(cfg, True)
    covers = {n: m[n] for n in _skin_names(cfg)}
    from boresight_case.geom import cylinder

    for b in through_bolts(cfg.barrels):
        x, _, z = b.centre
        for sign in (1, -1):
            ring = to_manifold(
                cylinder((x, sign * b.half, z), (0, sign, 0), 3.4, FLANGE - POCKET)
                - cylinder((x, sign * (b.half - 1), z), (0, sign, 0), 2.4, FLANGE + 2)
            )
            filled = sum(intersection_volume(ring, mm) for mm in covers.values())
            assert filled > 0.8 * ring.volume(), (b.name, sign)
        assert intersection_volume(m[b.name], m["receiver"]) < 0.5
        for name, mm in covers.items():
            assert intersection_volume(m[b.name], mm) < 0.5, (b.name, name)


@pytest.mark.parametrize("cfg", CORE_CONFIGS, ids=lambda c: c.name)
@pytest.mark.parametrize("style", STYLES)
def test_no_cover_touches_a_functional_part(cfg, style):
    """Covers rest on the bones' outside only, never on a board, camera,
    module, cell, the trigger or a lead: a restyle moves none of them."""
    cfg = Config(
        board=cfg.board,
        power=cfg.power,
        mechanism=cfg.mechanism,
        trigger=cfg.trigger,
        barrels=cfg.barrels,
        feedback=cfg.feedback,
        buttons=cfg.buttons,
        style=style,
    )
    a = assembly(cfg, True)
    m = everything(cfg, True)
    functional = {b.label for b in a.bought if b.vendor.functional}
    functional |= {
        n
        for n, p in a.printed.items()
        if p.kind == "core"
        and n not in ("receiver", "barrel", "barrel 2", "grip", "rear-cap")
    }
    functional |= set(a.leads)
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
    core_printed = {
        n: core[n]
        for n, p in assembly(Config()).printed.items()
        if p.part != "spacer-collar"
    }
    for part in module.printed:
        o = to_manifold(part.oriented())
        assert checks.overhangs(part.name, o) == [], part.name
        assert checks.bed_fit(part.name, o, cfg.printer.volume) == [], part.name
        mm = to_manifold(part.shape)
        for zone, zm in zone_meshes(Config()).items():
            assert checks.overlapping(zm, {part.name: mm}, "keep-out", zone) == []
        assert checks.overlapping(mm, core_printed, "interference", part.name) == []


def test_accents_are_trapped_between_a_cover_and_the_bone():
    cfg = Config(style="blaster")
    m = meshes(cfg, True)
    accents = [n for n in m if n.startswith("accent-")]
    assert len(accents) == 2
    covers = [n for n in _skin_names(cfg) if n.startswith("skin-")]
    for acc in accents:
        assert sum(intersection_volume(m[acc], m[s]) for s in covers) < 1.0
        assert intersection_volume(m[acc], m["receiver"]) < 1.0
        # Its flange is behind a cover: pulled outward it hits the cover.
        from build123d import Location

        side = 1 if "left" in acc else -1
        shape = assembly(cfg, True).printed[acc].shape
        pulled = to_manifold(Location((0, side * 1.5, 0)) * shape)
        assert sum(intersection_volume(pulled, m[s]) for s in covers) > 5.0


def test_restyling_replaces_only_cover_parts():
    a = assembly(Config(style="minimal"), True)
    b = assembly(Config(style="blaster"), True)
    core_a = {n: p.shape.volume for n, p in a.printed.items() if p.kind == "core"}
    core_b = {n: p.shape.volume for n, p in b.printed.items() if p.kind == "core"}
    assert core_a == core_b


def test_a_bench_build_uses_the_same_bolts_with_collars():
    cfg = Config()
    bench = assembly(cfg, False)
    covered = assembly(cfg, True)
    keys = lambda a: sorted(b.key for b in a.bought)  # noqa: E731
    assert keys(bench) == keys(covered)
    assert bench.part_counts()["spacer-collar"] == 2 * len(bench.bolts)
    assert checks.interference(meshes(cfg), bench.press_fits) == []
