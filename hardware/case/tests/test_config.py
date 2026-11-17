import subprocess
import sys
import textwrap

import pytest

from boresight_case import catalog
from boresight_case.config import (
    Config,
    ConfigError,
    Printer,
    from_dict,
    load,
    shipped_configurations,
)
from boresight_case.styles import STYLE_PARAMS


def test_defaults_are_a_valid_configuration():
    cfg = Config()
    assert (cfg.board, cfg.power, cfg.trigger, cfg.style) == (
        "esp32-cam",
        "aa",
        "mx",
        "minimal",
    )
    assert cfg.camera == "ov2640"
    assert cfg.printer == Printer()


def test_pi_with_batteries_is_refused_naming_board_drawer_and_reason():
    with pytest.raises(ConfigError) as e:
        from_dict({"build": {"board": "pi-zero-2w", "power": "aa"}})
    msg = str(e.value)
    assert "pi-zero-2w" in msg and "'aa'" in msg
    assert "USB cable" in msg and "power" in msg and "data" in msg


@pytest.mark.parametrize("power", ["aa", "aaa", "18650"])
def test_every_battery_drawer_is_refused_for_the_pi(power):
    with pytest.raises(ConfigError, match=power):
        Config(board="pi-zero-2w", power=power)


def test_esp32_cam_on_the_tether_is_accepted():
    cfg = from_dict({"build": {"board": "esp32-cam", "power": "usb"}})
    assert cfg.power == "usb"


def test_refusal_happens_before_any_geometry_is_imported():
    # Run in a fresh interpreter: the CAD kernel must not be loaded to
    # decide that a configuration is invalid.
    code = textwrap.dedent(
        """
        import sys
        from boresight_case.config import from_dict, ConfigError
        try:
            from_dict({"build": {"board": "pi-zero-2w", "power": "aa"}})
        except ConfigError:
            pass
        else:
            raise SystemExit("not refused")
        assert "build123d" not in sys.modules, "geometry was imported"
        assert "OCP" not in sys.modules, "the CAD kernel was imported"
        """
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_camera_is_only_chosen_for_the_pi():
    assert Config(board="pi-zero-2w", power="usb").camera == "cm3"
    assert Config(board="pi-zero-2w", power="usb", camera="cm2").camera == "cm2"
    with pytest.raises(ConfigError, match="only for the Pi kit"):
        Config(board="esp32-cam", camera="cm3")
    with pytest.raises(ConfigError, match="camera must be one of"):
        Config(board="pi-zero-2w", power="usb", camera="cm3-wide")


@pytest.mark.parametrize(
    "data, fragment",
    [
        ({"build": {"board": "luckfox"}}, "board must be one of"),
        ({"build": {"trigger": "tactile"}}, "trigger must be one of"),
        ({"build": {"style": "zapper"}}, "style must be one of"),
        ({"build": {"colour": "red"}}, "unknown [build] key 'colour'"),
        ({"bulid": {}}, "unknown section 'bulid'"),
        ({"printer": {"clearance": 2}}, "clearance must be 0 to 1 mm"),
        ({"printer": {"fastener": "glue"}}, "fastener must be one of"),
        ({"printer": {"volume": [180, 0, 180]}}, "volume"),
    ],
)
def test_bad_values_are_refused_with_the_key_named(data, fragment):
    with pytest.raises(ConfigError) as e:
        from_dict(data)
    assert fragment in str(e.value)


def test_out_of_range_style_parameter_names_the_parameter_and_range():
    with pytest.raises(ConfigError) as e:
        from_dict({"build": {"style": "minimal"}, "style": {"shroud_length": 45}})
    msg = str(e.value)
    assert "'shroud_length'" in msg and "0 to 20" in msg and "45" in msg


def test_wrong_type_and_unknown_style_parameters_are_refused():
    with pytest.raises(ConfigError, match="'accents' must be true or false"):
        Config(style="blaster", style_params={"accents": "yes"})
    with pytest.raises(ConfigError, match="'grip_texture' must be one of"):
        Config(style="minimal", style_params={"grip_texture": "knurl"})
    with pytest.raises(ConfigError, match="no parameter 'fins'"):
        Config(style="blaster", style_params={"fins": 3})
    with pytest.raises(ConfigError, match="'chamfer'"):
        Config(style="minimal", style_params={"chamfer": True})


@pytest.mark.parametrize("style", sorted(STYLE_PARAMS))
def test_both_ends_of_every_range_are_accepted(style):
    for p in STYLE_PARAMS[style]:
        if p.minimum is None:
            continue
        for value in (p.minimum, p.maximum):
            cfg = Config(style=style, style_params={p.name: value})
            assert cfg.style_params[p.name] == value


def test_defaults_fill_every_style_parameter():
    cfg = Config(style="blaster")
    assert set(cfg.style_params) == {p.name for p in STYLE_PARAMS["blaster"]}


def test_load_reads_a_toml_file(tmp_path):
    f = tmp_path / "gun.toml"
    f.write_text(
        textwrap.dedent(
            """
            [build]
            board = "pi-zero-2w"
            power = "usb"
            trigger = "microswitch"
            style = "blaster"
            camera = "cm2"

            [style]
            shroud_length = 20

            [printer]
            volume = [220, 220, 250]
            clearance = 0.3
            fastener = "insert"
            """
        )
    )
    cfg = load(f)
    assert cfg.board == "pi-zero-2w" and cfg.camera == "cm2"
    assert cfg.style_params["shroud_length"] == 20.0
    assert cfg.printer == Printer(
        volume=(220.0, 220.0, 250.0), clearance=0.3, fastener="insert"
    )


def test_load_reports_unreadable_and_invalid_files(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load(tmp_path / "missing.toml")
    bad = tmp_path / "bad.toml"
    bad.write_text("[build\n")
    with pytest.raises(ConfigError, match="not valid TOML"):
        load(bad)


def test_shipped_configurations_are_every_valid_combination():
    configs = shipped_configurations()
    # ESP32-CAM: 4 drawers x 2 switches x 2 styles; Pi: tether only,
    # 2 cameras x 2 switches x 2 styles.
    # (ESP32-CAM: 4 drawers; Pi: tether only, 2 cameras) x 3 mechanisms
    # x 2 switches x 2 styles.
    assert len(configs) == (4 + 2) * 3 * 2 * 2
    assert len({c.name for c in configs}) == len(configs)
    assert all(c.power == "usb" for c in configs if c.board == "pi-zero-2w")


def test_part_names_follow_the_configuration():
    pi = Config(board="pi-zero-2w", power="usb", trigger="mx", style="minimal")
    names = catalog.part_names(pi)
    assert "sled-pi-zero-2w" in names and "bulkhead-pi-camera" in names
    assert "drawer-usb" in names and "switch-plate-mx" in names
    assert not any(n.startswith("drawer-a") or "esp32" in n for n in names)
    assert len([n for n in names if n.startswith("skin-minimal-")]) == 6
    esp = Config(style="blaster")
    names = catalog.part_names(esp)
    assert "sled-pi-zero-2w" not in names and "bulkhead-esp32-cam" in names
    assert "accent-blaster-muzzle-ring" in names
    no_accents = Config(style="blaster", style_params={"accents": False})
    assert not any(n.startswith("accent-") for n in catalog.part_names(no_accents))


def test_mechanism_is_chosen_and_checked():
    assert Config().mechanism == "filament"
    cfg = from_dict({"build": {"mechanism": "button", "trigger": "microswitch"}})
    assert cfg.mechanism == "button"
    assert cfg.name == "esp32-cam_aa_button-microswitch_minimal"
    with pytest.raises(ConfigError, match="mechanism must be one of"):
        Config(mechanism="spring")


@pytest.mark.parametrize("mechanism", ["filament", "bolt", "button"])
def test_each_configuration_lists_only_its_mechanisms_parts(mechanism):
    names = catalog.part_names(Config(mechanism=mechanism))
    own = set(catalog.MECHANISM_PARTS[mechanism])
    others = set().union(*catalog.MECHANISM_PARTS.values()) - own
    assert own <= set(names)
    assert not others & set(names)
