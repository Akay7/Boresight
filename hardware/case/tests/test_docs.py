"""The case README agrees with the code it describes."""

import itertools
import re
import tomllib
from pathlib import Path

from boresight_case import catalog
from boresight_case.config import (
    MECHANISMS,
    POWERS,
    TRIGGERS,
    VALID_POWERS,
    shipped_configurations,
)
from boresight_case.interfaces import Fit
from boresight_case.parts.trigger import trigger_module

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
README = (ROOT / "README.md").read_text()


def section(title: str) -> str:
    start = README.index(f"\n## {title}\n")
    rest = README[start + 4 :]
    nxt = rest.find("\n## ")
    return rest if nxt < 0 else rest[:nxt]


def test_every_module_part_named_in_the_readme_exists():
    names = {n for cfg in shipped_configurations() for n in catalog.part_names(cfg)}
    table = section("Modules").split("### Fasteners")[0]
    for cell in re.findall(r"`([a-z0-9*-]+)`", table):
        pattern = re.compile("^" + cell.replace("*", ".+") + "$")
        assert any(pattern.match(n) for n in names), cell


def test_cassette_steps_name_its_purchased_parts():
    text = section("The trigger")
    for mechanism, trigger in itertools.product(MECHANISMS, TRIGGERS):
        for b in trigger_module(Fit(), mechanism, trigger).bought:
            if "nut" in b.label:
                continue
            assert b.label in text, b.label


def test_esp32_wiring_matches_the_firmware_defaults():
    kconfig = (REPO / "firmware/boresight-cam/main/Kconfig.projbuild").read_text()
    block = kconfig[kconfig.index("config BORESIGHT_TRIGGER_GPIO") :]
    default = re.search(r"default (\d+)", block).group(1)
    assert f"GPIO{default} and GND" in section("The board kits")


def test_pi_wiring_matches_the_gun_defaults():
    pins = tomllib.loads((REPO / "deploy/pi/boresight-gun.example.toml").read_text())[
        "pins"
    ]
    text = section("The board kits")
    assert f"GPIO{pins['trigger']} (pin 11)" in text
    assert f"GPIO{pins['led']} (pin 13)" in text


def test_drawer_table_matches_the_valid_configurations():
    table = section("Power")
    rows = dict(re.findall(r"^\| `([a-z0-9]+)` \| ([^|]+) \|", table, re.M))
    assert set(rows) == set(POWERS)
    for power, who in rows.items():
        assert ("Pi" in who) == (power in VALID_POWERS["pi-zero-2w"]), power
        assert "ESP32-CAM" in who


def test_skin_guide_names_every_zone_and_attachment_point():
    from boresight_case.export import interface_data

    guide = section("Skins")
    data = interface_data(shipped_configurations()[0])
    for z in data["keep_out_zones"]:
        assert f"`{z['name']}`" in guide, z["name"]
    for p in data["attachment_points"]:
        assert f"`{p['name']}`" in guide, p["name"]


def test_style_table_matches_the_parameters():
    from boresight_case.styles import STYLE_PARAMS

    table = section("Skins")
    for style, params in STYLE_PARAMS.items():
        for p in params:
            assert f"| `{style}` | `{p.name}` |" in table, (style, p.name)
            if p.minimum is not None:
                assert f"{p.minimum:g} to {p.maximum:g}" in table, (style, p.name)


def test_documented_commands_parse():
    import shlex

    from boresight_case.cli import _parser

    commands = [
        line.strip()
        for line in README.splitlines()
        if line.strip().startswith("uv run boresight-case ")
    ]
    assert len(commands) >= 5
    for line in commands:
        args = shlex.split(line, comments=True)[3:]
        _parser().parse_args(args)


def test_repository_readmes_point_to_the_case():
    readme = (REPO / "README.md").read_text()
    assert "](hardware/case/README.md)" in readme
    assert "(#the-printed-case)" in readme and "\n## The printed case\n" in readme
    pi = (REPO / "deploy/pi/README.md").read_text()
    assert "](../../hardware/case/README.md)" in pi
    assert (REPO / "deploy/pi/../../hardware/case/README.md").resolve().exists()
    # The pins they quote are the case README's.
    case = section("The board kits")
    for pin in ("GPIO13", "GPIO17 (pin 11)", "GPIO27 (pin 13)"):
        assert pin in readme and pin in case, pin


# The scenarios of the specification that only a printed, assembled gun can
# confirm. Each must still exist in the specs and appear in the checklist.
HAND_CHECKED = (
    "Tuning before the full print",
    "Slicing with supports off",
    "Loading a part",
    "Shopping for an AA ESP32-CAM gun",
    "Printing without Python",
    "Bench test without skins",
    "A full teardown and rebuild",
    "Twenty rebuilds",
    "Removing the trigger cassette",
    "Changing from the filament pin to a bolt",
    "A button instead of a lever",
    "Converting an ESP32-CAM gun to a Pi gun",
    "Flashing without unsoldering",
    "Either camera module fits",
    "Swapping the SD card",
    "A tug on the cable",
    "Temperature after a long session",
    "No vignetting",
    "No software change",
    "Checking the solve state while aiming",
    "Changing battery type",
    "A reversed drawer does not go in",
    "Swapping AA cells",
    "Nearly flat NiMH cells",
    "Switching off",
    "Charging overnight",
    "Running the cell down",
    "Fitting an MX-style switch",
    "Changing to a microswitch",
    "A hard pull",
    "Release with a light microswitch",
    "Changing style on an assembled gun",
    "A skin's screws line up",
    "Battery swap with skins on",
    "A two-colour gun",
    "Restyling keeps the zero",
)


def test_every_hand_checked_scenario_is_on_the_checklist():
    specs = REPO / "openspec"
    texts = "\n".join(
        p.read_text() for p in specs.rglob("spec.md") if "case-" in str(p.parent.name)
    )
    checklist = " ".join(section("What only a printed gun can confirm").split())
    for name in HAND_CHECKED:
        assert f"#### Scenario: {name}" in texts, name
        assert f"*{name}*" in checklist, name
