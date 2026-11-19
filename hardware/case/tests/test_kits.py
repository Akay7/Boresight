"""The board kits (tasks 9.1 to 9.3, 10.1, 10.2)."""

import pytest
from conftest import ESP32_DRAWERS, PI_CAMERAS, assembly, meshes, oriented

from boresight_case import checks
from boresight_case import layout as L
from boresight_case.config import Config
from boresight_case.geom import box
from boresight_case.joints import barrel_port
from boresight_case.mesh import intersection_volume, to_manifold
from boresight_case.parts import kits
from boresight_case.vendor import SD_CARD_PROTRUDE

PI = Config(board="pi-zero-2w")
ESP = Config()


def _printed(cfg, skins=False):
    a = assembly(cfg, skins)
    return {n: m for n, m in meshes(cfg, skins).items() if n in a.printed}


@pytest.mark.parametrize("cfg", [ESP, PI], ids=lambda c: c.board)
def test_kit_parts_print_without_support(cfg):
    for name, p in assembly(cfg).printed.items():
        if p.module in ("camera", "sled", "pi-retainer", "clamp", "nose"):
            assert checks.overhangs(name, oriented(cfg, name)) == [], name
            assert (
                checks.bed_fit(name, oriented(cfg, name), cfg.printer.volume) == []
            ), name


# -- the Pi kit ----------------------------------------------------------------------


@pytest.mark.parametrize("cfg", PI_CAMERAS, ids=lambda c: c.camera)
def test_either_camera_module_sits_on_the_same_standoffs_and_sees_out(cfg):
    m = meshes(cfg)
    assert intersection_volume(m["camera"], m["camera-pi"]) < 1.0
    view = to_manifold(kits.frustum(cfg.camera))
    assert checks.overlapping(view, _printed(cfg), "field of view", cfg.camera) == []


def test_the_pi_rides_its_sled_in_the_barrel_ports_down():
    a = assembly(PI)
    pi = a.bought_by_label()["Pi Zero 2 W"].shape.bounding_box()
    x0, x1 = L.barrel_x(0)
    assert x0 < pi.min.X and pi.max.X < x1 - L.PORT_DEPTH
    assert pi.min.Z < L.PI_Z0  # its ports, below its port edge


def test_the_sd_card_comes_out_with_only_the_barrel_off():
    """The card's way straight back out of the Pi meets nothing printed in
    the barrel."""
    card = kits.pi_location() * box(-SD_CARD_PROTRUDE, 12, 10.5, 22.5, 1.4, 2.8)
    bb = card.bounding_box()
    path = box(bb.min.X - 20, bb.min.X + 0.5, bb.min.Y, bb.max.Y, bb.min.Z, bb.max.Z)
    barrel_side = {
        n: mm
        for n, mm in _printed(PI).items()
        if n in ("barrel", "sled-pi-zero-2w", "pi-retainer", "camera-pi")
    }
    hits = checks.overlapping(to_manifold(path), barrel_side, "sd path", "sd card", 0.1)
    assert hits == []


def test_the_pi_camera_board_clears_the_muzzle_bolts_crush_tubes():
    """The open check: the camera board's edge to the muzzle port's crush
    tubes, expected about 1 mm, at least 0.5."""
    camera = meshes(PI)["camera"]
    tubes = to_manifold(
        barrel_port(0).bolts[0].crush_tube(-12.75, 12.75, kits.MODULE_UP)
        + barrel_port(0).bolts[1].crush_tube(-12.75, 12.75, kits.MODULE_UP)
    )
    assert camera.min_gap(tubes, 3.0) >= 0.5


@pytest.mark.parametrize(
    "cfg", [PI, Config(board="pi-zero-2w", barrels=2)], ids=lambda c: str(c.barrels)
)
def test_every_plug_reaches_its_port_through_the_window_with_covers(cfg):
    m = meshes(cfg, True)
    printed = _printed(cfg, True)
    for plug in ("HDMI plug", "USB plug", "power plug"):
        assert checks.overlapping(m[plug], printed, "plug", plug) == [], plug
        assert m[plug].min_gap(m["Pi Zero 2 W"], 0.5) < 0.05


def test_a_short_window_fails_naming_the_plug():
    from boresight_case.geom import NEG_X

    a = assembly(PI)
    barrel = a.printed["barrel"].shape
    # Close the window's first 10 mm: the HDMI plug no longer passes.
    x0 = L.WINDOW_X[0]
    filled = barrel + box(x0, x0 + 15.0, *L.WINDOW_Y, L.FLOOR_Z, L.FLOOR_IN)
    hits = checks.overlapping(
        to_manifold(filled), {"HDMI plug": meshes(PI)["HDMI plug"]}, "plug", "barrel"
    )
    assert [h.parts for h in hits] == [("HDMI plug", "barrel")]
    assert NEG_X  # the barrel prints standing on its muzzle


def test_the_clamp_bar_holds_the_cables_under_the_barrel():
    m = meshes(PI)
    assert m["clamp thumbscrew"].min_gap(m["nut, clamp"], 1.0) < 0.05
    assert intersection_volume(m["cable-clamp"], m["barrel"]) < 0.5
    clamp = assembly(PI).printed["cable-clamp"].shape.bounding_box()
    assert clamp.max.Z <= L.FLOOR_Z + 0.01


def test_the_pi_and_its_heatsink_face_the_vents():
    from boresight_case.keepouts import zones

    heatsink = assembly(PI).bought_by_label()["heatsink"].shape.bounding_box()
    vents = zones(PI)["vents"].bounding_box()
    assert vents.min.X <= heatsink.min.X and heatsink.max.X <= vents.max.X


# -- the ESP32-CAM nose ----------------------------------------------------------------


def test_the_nose_holds_the_board_24_mm_ahead_of_the_muzzle_antenna_down():
    board = assembly(ESP).bought_by_label()["ESP32-CAM"].shape.bounding_box()
    assert board.min.X == pytest.approx(
        L.muzzle_x(1) + L.NOSE_BOARD_BACK - 8.5, abs=0.01
    )
    from boresight_case.keepouts import antenna_solids

    antenna = antenna_solids()["esp32-cam"].bounding_box()
    assert antenna.max.Z < 0  # down


def test_the_header_plugs_clear_the_port_bolts_by_2_mm():
    m = meshes(ESP)
    for plug in ("hub plug", "debug plug"):
        for b in barrel_port(0).bolts:
            assert m[plug].min_gap(m[b.name], 5.0) >= 2.0, (plug, b.name)


def test_the_board_and_its_parts_fit_the_nose():
    m = meshes(ESP)
    for part in (
        "ESP32-CAM",
        "camera",
        "capacitor",
        "light guide",
        "debug socket",
        "BOOT button",
        "debug board",
    ):
        for printed in ("nose-esp32-cam", "nose-sleeve", "barrel"):
            assert intersection_volume(m[part], m[printed]) < 1.0, (part, printed)


def test_the_debug_socket_and_boot_button_open_on_the_noses_top():
    a = assembly(ESP)
    top = L.HALF_H
    socket = a.bought_by_label()["debug socket"].shape.bounding_box()
    boot = a.bought_by_label()["BOOT button"].shape.bounding_box()
    assert socket.max.Z == pytest.approx(top - L.WALL, abs=0.01)
    assert boot.max.Z > top


def test_the_ov2640_view_is_clear():
    view = to_manifold(kits.frustum("ov2640"))
    assert checks.overlapping(view, _printed(ESP), "field of view", "ov2640") == []


@pytest.mark.parametrize("cfg", ESP32_DRAWERS, ids=lambda c: c.power)
def test_the_esp32_cam_kit_fits_every_drawer(cfg):
    assert checks.interference(meshes(cfg), assembly(cfg).press_fits) == []


def test_the_compact_gun_is_142_mm_long():
    cfg = Config(barrels=0)
    a = assembly(cfg)
    lo = a.printed["rear-cap"].shape.bounding_box().min.X
    hi = max(p.shape.bounding_box().max.X for p in a.printed.values())
    assert abs((hi - lo) - 142.0) <= 5.0, hi - lo
    standard = assembly(Config())
    hi1 = max(p.shape.bounding_box().max.X for p in standard.printed.values())
    assert abs((hi1 - lo) - 242.0) <= 5.0


def test_the_nose_and_the_pi_camera_module_take_the_ports_tenon():
    """Each fills the muzzle port with the standard tenon's outside."""
    for cfg, name in ((ESP, "nose-esp32-cam"), (PI, "camera-pi")):
        m = meshes(cfg)
        assert intersection_volume(m[name], m["barrel"]) < 0.5
