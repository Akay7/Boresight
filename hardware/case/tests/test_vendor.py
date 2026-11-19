import pytest

from boresight_case.mesh import to_manifold
from boresight_case.vendor import CONSUMABLES, VENDOR


@pytest.mark.parametrize("key", sorted(VENDOR))
def test_every_envelope_is_one_closed_solid(key):
    shape = VENDOR[key].build()
    assert shape.is_valid
    assert len(shape.solids()) == 1
    man = to_manifold(shape)
    assert man.volume() == pytest.approx(shape.volume, rel=0.02)


@pytest.mark.parametrize("key", sorted(VENDOR))
def test_every_entry_says_where_its_dimensions_came_from(key):
    part = VENDOR[key]
    assert part.source.split(":")[0] in {"datasheet", "caliper", "listing"}
    assert len(part.source.split(":", 1)[1].strip()) > 5
    assert part.spec


def test_cameras_carry_their_field_of_view():
    for key in ("ov2640", "picam-cm2", "picam-cm3"):
        dims = VENDOR[key].dims
        assert 30 < dims["vfov"] < dims["hfov"] < 90
        assert dims["lens_front"] > 0


def test_consumables_are_described():
    assert all(text for text in CONSUMABLES.values())


def test_both_boards_antennas_are_solids_the_antenna_check_can_use():
    from boresight_case.keepouts import antenna_solids

    for board, solid in antenna_solids().items():
        assert solid.is_valid and solid.volume > 20, board
    for key in ("esp32-cam", "pi-zero-2w"):
        assert VENDOR[key].metal


def test_the_esp32_cams_header_rows_name_every_pin_the_plugs_use():
    from boresight_case.vendor import esp32_plug_pins

    assert esp32_plug_pins("hub") == ("5V", "GND", "IO12", "IO13", "IO15", "IO14")
    assert esp32_plug_pins("debug") == ("IO0", "GND", "VCC", "U0R", "U0T", "GND")
