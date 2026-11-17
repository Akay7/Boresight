"""The board kits (tasks 7.1, 7.2, 7.3)."""

import pytest
from build123d import Location
from conftest import ESP32_DRAWERS, PI_CAMERAS, assembly, meshes, oriented

from boresight_case import checks
from boresight_case import layout as L
from boresight_case.config import Config
from boresight_case.geom import box
from boresight_case.keepouts import zones
from boresight_case.mesh import intersection_volume, to_manifold
from boresight_case.parts import kits
from boresight_case.parts.receiver import _vents
from boresight_case.vendor import ESP32_ANTENNA, ESP32_PINS, SD_CARD_PROTRUDE


def _printed(cfg):
    a = assembly(cfg)
    return {n: m for n, m in meshes(cfg).items() if n in a.printed}


@pytest.mark.parametrize("cfg", [ESP32_DRAWERS[0], *PI_CAMERAS], ids=lambda c: c.name)
def test_bulkhead_and_sled_print_without_support(cfg):
    names = [n for n in assembly(cfg).printed if n.startswith(("bulkhead", "sled"))]
    for name in names:
        assert checks.overhangs(name, oriented(cfg, name)) == []
        assert checks.bed_fit(name, oriented(cfg, name), cfg.printer.volume) == []


def test_esp32_board_fits_its_bulkhead():
    m = meshes(ESP32_DRAWERS[0])
    for part in ("ESP32-CAM", "camera", "capacitor", "light guide"):
        assert intersection_volume(m[part], m["bulkhead-esp32-cam"]) < 1.0, part
        assert intersection_volume(m[part], m["barrel"]) < 1.0, part


def test_ov2640_view_is_clear():
    cfg = ESP32_DRAWERS[0]
    view = to_manifold(kits.frustum("ov2640"))
    assert checks.overlapping(view, _printed(cfg), "field of view", "ov2640") == []


@pytest.mark.parametrize("cfg", ESP32_DRAWERS, ids=lambda c: c.power)
def test_no_metal_within_10_mm_of_the_antenna(cfg):
    x0, x1, y0, y1, z0, z1 = ESP32_ANTENNA
    antenna = to_manifold(kits.esp32_location() * box(x0, x1, y0, y1, z0, z1))
    a = assembly(cfg)
    m = meshes(cfg)
    metal = {
        b.label: m[b.label]
        for b in a.bought
        if b.vendor.metal and b.label != "ESP32-CAM"
    }
    assert checks.too_close("antenna", antenna, metal, 10.0, "antenna") == []


def test_header_pins_take_plug_on_leads():
    """Each used pin's plug-on lead, with room to bend its wire, is clear
    of printed material, so the board can be reflashed without solder."""
    m = meshes(ESP32_DRAWERS[0])
    printed = _printed(ESP32_DRAWERS[0])
    for pin in ESP32_PINS:
        lead = {f"lead on {pin}": m[f"lead on {pin}"]}
        for name, part in printed.items():
            assert checks.overlapping(part, lead, "lead", name) == [], (pin, name)


@pytest.mark.parametrize("cfg", PI_CAMERAS, ids=lambda c: c.camera)
def test_camera_module_fits_the_shared_pegs_and_sees_out(cfg):
    m = meshes(cfg)
    assert intersection_volume(m["camera"], m["bulkhead-pi-camera"]) < 1.0
    view = to_manifold(kits.frustum(cfg.camera))
    assert checks.overlapping(view, _printed(cfg), "field of view", cfg.camera) == []


def test_both_camera_modules_use_the_same_bulkhead():
    a = assembly(PI_CAMERAS[0]).printed["bulkhead-pi-camera"].shape
    b = assembly(PI_CAMERAS[1]).printed["bulkhead-pi-camera"].shape
    assert a.volume == pytest.approx(b.volume)


@pytest.mark.parametrize("cfg", PI_CAMERAS, ids=lambda c: c.camera)
def test_pi_heatsink_plug_and_cable_fit(cfg):
    m = meshes(cfg)
    printed = _printed(cfg)
    for part in (
        "Pi Zero 2 W",
        "heatsink",
        "USB plug",
        "lead on pins 9-11-13",
        "usb cable",
    ):
        assert checks.overlapping(m[part], printed, "fit", part) == [], part


def test_sd_card_comes_out_with_only_the_rear_cap_off():
    """The card's path straight back out of the Pi meets no printed part
    but the rear cap."""
    cfg = PI_CAMERAS[1]
    card = kits.pi_location() * box(-SD_CARD_PROTRUDE, 12, 10.5, 22.5, 1.4, 2.8)
    bb = card.bounding_box()
    path = box(bb.min.X - 40, bb.min.X + 0.5, bb.min.Y, bb.max.Y, bb.min.Z, bb.max.Z)
    hits = checks.overlapping(
        to_manifold(path), _printed(cfg), "sd path", "sd card", 0.1
    )
    assert {p.parts[0] for p in hits} == {"rear-cap"}


def test_vents_lie_inside_the_vent_zone():
    """Every slot opens into the zone: pushed out through its wall, each
    slot lies wholly inside it."""
    from build123d import Location as Loc

    zone = to_manifold(zones()["vents"])
    vents = _vents()
    side = to_manifold(Loc((0, -3.0, 0)) * vents) ^ to_manifold(
        box(-200, 0, -100, -L.HALF_W, -100, 100)
    )
    top = to_manifold(Loc((0, 0, 3.0)) * vents) ^ to_manifold(
        box(-200, 0, -100, 100, L.HALF_H, 100)
    )
    assert side.volume() > 10 and top.volume() > 10
    assert (side - zone).volume() < 0.1
    assert (top - zone).volume() < 0.1


def test_pi_vents_face_the_processor():
    x0, x1 = L.SOC_VENT_X
    soc_x = L.PI_X0 + 30.0
    assert x0 <= soc_x <= x1


def test_light_guide_reaches_the_barrel_window():
    m = meshes(ESP32_DRAWERS[0])
    guide = (
        assembly(ESP32_DRAWERS[0]).bought_by_label()["light guide"].shape.bounding_box()
    )
    assert guide.max.Z > L.HALF_H  # it pokes out through the barrel's top
    assert m["light guide"].min_gap(m["barrel"], 1.0) > 0


def test_esp32_board_rests_on_the_floor_of_its_bulkhead():
    board = assembly(Config()).bought_by_label()["ESP32-CAM"].shape.bounding_box()
    assert board.max.Z < L.IN_HALF_H
    loc = kits.esp32_location()
    assert isinstance(loc, Location)
