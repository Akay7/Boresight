"""The gun's configuration: defaults, overrides and every way it can be wrong."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boresight.gun.config import ConfigError, load, parse_config
from boresight.lens import LensModel
from boresight.zeroing import Zero


def _lens(size=(640, 480)) -> LensModel:
    import numpy as np

    return LensModel(
        camera_matrix=np.array(
            [[500.0, 0, size[0] / 2], [0, 500.0, size[1] / 2], [0, 0, 1]]
        ),
        dist_coeffs=np.zeros(5),
        image_size=size,
    )


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "gun.toml"
    path.write_text(text)
    return path


def test_defaults_match_the_servers_where_they_overlap() -> None:
    from boresight.aim_hold import DEFAULT_HOLD_S
    from boresight.one_euro import OneEuroFilter

    config = parse_config({})

    assert config.tuning.hold_s == DEFAULT_HOLD_S
    assert config.tuning.min_cutoff == OneEuroFilter().min_cutoff
    assert config.tuning.beta == OneEuroFilter().beta
    assert (config.pins.trigger, config.pins.led) == (17, 27)
    assert config.lens_file is None and config.zero_file is None


def test_the_shipped_layout_is_the_default() -> None:
    loaded = load(None)

    assert loaded.marker_map is not None
    assert loaded.lens is None and loaded.zero is None


def test_a_file_overrides_defaults(tmp_path) -> None:
    path = _write(
        tmp_path,
        "[camera]\nwidth = 800\nheight = 600\n\n[pins]\ntrigger = 5\n"
        "[tuning]\nsmoothing = false\n",
    )

    config = load(path).config

    assert (config.camera.width, config.camera.height) == (800, 600)
    assert config.pins.trigger == 5
    assert config.tuning.smoothing is False
    assert config.camera.fps == 30  # untouched


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("nonsense = 1", "unknown key"),
        ("[camera]\nbogus = 1", "unknown key"),
        ("[camera]\nwidth = 0", "positive"),
        ("[pins]\ndebounce_ms = 0", "debounce"),
        ("layout = '/nonexistent/markers.toml'", "marker layout"),
        ("this is not toml", "not valid TOML"),
    ],
)
def test_bad_configuration_is_refused_with_the_reason(tmp_path, text, message) -> None:
    with pytest.raises(ConfigError, match=message):
        load(_write(tmp_path, text))


def test_an_invalid_marker_layout_is_refused(tmp_path) -> None:
    layout = tmp_path / "markers.toml"
    layout.write_text("screen_width_mm = -1\n")

    with pytest.raises(ConfigError, match="marker layout"):
        load(_write(tmp_path, f"layout = '{layout}'"))


def test_a_lens_file_the_server_wrote_is_used(tmp_path) -> None:
    lens_file = tmp_path / "lens.json"
    lens_file.write_text(json.dumps({"phone|cam|640x480": _lens().as_dict()}))

    loaded = load(_write(tmp_path, f"lens_file = '{lens_file}'"))

    assert loaded.lens is not None
    assert tuple(loaded.lens.image_size) == (640, 480)


def test_a_lens_store_with_several_entries_needs_a_key(tmp_path) -> None:
    lens_file = tmp_path / "lens.json"
    lens_file.write_text(
        json.dumps({"a|x|640x480": _lens().as_dict(), "b|y|640x480": _lens().as_dict()})
    )

    with pytest.raises(ConfigError, match="lens_key"):
        load(_write(tmp_path, f"lens_file = '{lens_file}'"))
    assert load(
        _write(tmp_path, f"lens_file = '{lens_file}'\nlens_key = 'b|y|640x480'")
    ).lens


def test_a_lens_made_at_another_resolution_is_refused(tmp_path) -> None:
    lens_file = tmp_path / "lens.json"
    lens_file.write_text(json.dumps({"k": _lens((1024, 768)).as_dict()}))

    with pytest.raises(ConfigError, match="never rescaled"):
        load(_write(tmp_path, f"lens_file = '{lens_file}'"))


def test_a_zero_file_the_server_wrote_is_used(tmp_path) -> None:
    zero_file = tmp_path / "zero.json"
    zero = Zero(offset=(0.01, -0.02), parallax=(0.0, 0.03), shots=5)
    zero_file.write_text(json.dumps({"version": 1, "clients": {"gun": zero.as_dict()}}))

    loaded = load(_write(tmp_path, f"zero_file = '{zero_file}'"))

    assert loaded.zero == zero


def test_a_broken_calibration_file_stops_startup(tmp_path) -> None:
    broken = tmp_path / "zero.json"
    broken.write_text("{not json")

    with pytest.raises(ConfigError, match="zero file"):
        load(_write(tmp_path, f"zero_file = '{broken}'"))
