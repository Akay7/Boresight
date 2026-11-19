import subprocess
import sys
import textwrap

import pytest

from boresight_case import catalog
from boresight_case.config import (
    BOARDS,
    MECHANISMS,
    POWERS,
    TRIGGERS,
    Config,
    ConfigError,
    Printer,
    from_dict,
    load,
    shipped_configurations,
)
from boresight_case.styles import STYLE_PARAMS, STYLES


def test_defaults_build_a_standard_esp32_cam_gun():
    cfg = Config()
    assert (cfg.board, cfg.power, cfg.mechanism, cfg.trigger, cfg.style) == (
        "esp32-cam",
        "aa",
        "bolt",
        "mx",
        "minimal",
    )
    assert (cfg.barrels, cfg.feedback, cfg.buttons) == (1, "none", False)
    assert cfg.camera == "ov2640"
    assert cfg.printer == Printer()


def test_the_filament_mechanism_is_refused_naming_its_replacement():
    with pytest.raises(ConfigError) as e:
        from_dict({"build": {"mechanism": "filament"}})
    assert "'filament'" in str(e.value) and "bolt" in str(e.value)


@pytest.mark.parametrize("power", POWERS)
def test_the_pi_takes_every_drawer(power):
    cfg = from_dict({"build": {"board": "pi-zero-2w", "power": power}})
    assert cfg.power == power and cfg.barrels == 1


def test_a_pi_with_no_barrel_is_refused_naming_board_barrels_and_reason():
    with pytest.raises(ConfigError) as e:
        from_dict({"build": {"board": "pi-zero-2w", "barrels": 0}})
    msg = str(e.value)
    assert "pi-zero-2w" in msg and "barrels = 0" in msg and "barrel" in msg
    assert "sled" in msg


def test_a_solenoid_on_the_tether_is_refused_naming_device_drawer_and_reason():
    with pytest.raises(ConfigError) as e:
        from_dict({"build": {"feedback": "solenoid", "power": "usb"}})
    msg = str(e.value)
    assert "'solenoid'" in msg and "'usb'" in msg and "cells" in msg


def test_buttons_are_for_the_pi_only():
    assert Config(board="pi-zero-2w", buttons=True).buttons
    with pytest.raises(ConfigError) as e:
        Config(board="esp32-cam", buttons=True)
    assert "pi-zero-2w" in str(e.value) and "'esp32-cam'" in str(e.value)


def test_an_esp32_cam_on_the_tether_is_accepted():
    assert Config(power="usb").power == "usb"


@pytest.mark.parametrize(
    "data",
    [
        {"build": {"board": "pi-zero-2w", "barrels": 0}},
        {"build": {"feedback": "solenoid", "power": "usb"}},
        {"build": {"buttons": True}},
        {"build": {"mechanism": "filament"}},
    ],
)
def test_refusal_happens_before_any_geometry_is_imported(data):
    # A fresh interpreter: the CAD kernel must not be loaded to decide
    # that a configuration is invalid.
    code = textwrap.dedent(
        f"""
        import sys
        from boresight_case.config import from_dict, ConfigError
        try:
            from_dict({data!r})
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
    assert Config(board="pi-zero-2w").camera == "cm3"
    assert Config(board="pi-zero-2w", camera="cm2").camera == "cm2"
    with pytest.raises(ConfigError, match="only for the Pi kit"):
        Config(board="esp32-cam", camera="cm3")
    with pytest.raises(ConfigError, match="camera must be one of"):
        Config(board="pi-zero-2w", camera="cm3-wide")


@pytest.mark.parametrize(
    "data, fragment",
    [
        ({"build": {"board": "luckfox"}}, "board must be one of"),
        ({"build": {"trigger": "tactile"}}, "trigger must be one of"),
        ({"build": {"style": "zapper"}}, "style must be one of"),
        ({"build": {"barrels": 3}}, "barrels must be 0, 1 or 2"),
        ({"build": {"barrels": True}}, "barrels must be 0, 1 or 2"),
        ({"build": {"feedback": "rumble"}}, "feedback must be one of"),
        ({"build": {"buttons": "yes"}}, "buttons must be true or false"),
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


def test_load_reads_a_toml_file(tmp_path):
    f = tmp_path / "gun.toml"
    f.write_text(
        textwrap.dedent(
            """
            [build]
            board = "pi-zero-2w"
            power = "18650"
            trigger = "microswitch"
            mechanism = "button"
            style = "blaster"
            camera = "cm2"
            barrels = 2
            feedback = "lra"
            buttons = true

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
    assert cfg.board == "pi-zero-2w" and cfg.camera == "cm2" and cfg.power == "18650"
    assert (cfg.barrels, cfg.feedback, cfg.buttons) == (2, "lra", True)
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


def test_the_shipped_set_follows_its_rule():
    configs = shipped_configurations()
    # The full set at one barrel: 2 boards x 4 drawers x 2 mechanisms x 2
    # plates x 2 styles. Then, with the default trigger and style: the
    # other barrel counts (no compact Pi), each feedback device (no solenoid
    # on the tether), the buttons on the Pi, and the Pi's other camera.
    full = 2 * 4 * 2 * 2 * 2
    barrels = 4 * 2 + 4 * 1
    feedback = 2 * (4 + 4 + 3)
    assert len(configs) == full + barrels + feedback + 4 + 1 == 103
    assert len({c.name for c in configs}) == len(configs)
    import itertools

    for board, power, mechanism, trigger, style in itertools.product(
        BOARDS, POWERS, MECHANISMS, TRIGGERS, STYLES
    ):
        assert (
            Config(
                board=board,
                power=power,
                mechanism=mechanism,
                trigger=trigger,
                style=style,
            )
            in configs
        )


def test_part_names_follow_the_configuration():
    pi = Config(board="pi-zero-2w", power="18650", buttons=True, feedback="solenoid")
    counts = catalog.part_counts(pi)
    assert {"sled-pi-zero-2w", "camera-pi", "pi-retainer", "cable-clamp"} <= set(counts)
    assert {
        "button-panel",
        "feedback-solenoid",
        "solenoid-strap",
        "drawer-18650",
    } <= set(counts)
    assert not any("esp32" in n or n.startswith("nose") for n in counts)
    long = catalog.part_counts(Config(barrels=2))
    assert long["barrel"] == 2 and long["skin-minimal-barrel-left"] == 2
    compact = catalog.part_counts(Config(barrels=0))
    assert "barrel" not in compact and not any("-barrel-" in n for n in compact)
    bench = catalog.part_counts(Config(), skins=False)
    assert bench["spacer-collar"] == 2 * 8
    assert "accent-blaster-stripe-left" in catalog.part_names(Config(style="blaster"))


def test_names_add_only_what_differs_from_the_default():
    assert Config().name == "esp32-cam_aa_bolt-mx_minimal"
    cfg = Config(board="pi-zero-2w", barrels=2, feedback="lra", buttons=True)
    assert cfg.name == "pi-cm3_aa_bolt-mx_minimal_long_lra_buttons"
    assert Config(barrels=0).name.endswith("_compact")
