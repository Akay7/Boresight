import subprocess
import sys

from boresight_case.cli import main


def test_help_lists_the_subcommands():
    out = subprocess.run(
        [sys.executable, "-m", "boresight_case.cli", "build", "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "--all" in out and "--out" in out and "--dry-run" in out


def test_invalid_file_exits_nonzero_with_the_validation_message(tmp_path, capsys):
    f = tmp_path / "gun.toml"
    f.write_text('[build]\nboard = "pi-zero-2w"\npower = "18650"\n')
    assert main(["build", str(f), "--dry-run"]) == 2
    err = capsys.readouterr().err
    assert "pi-zero-2w" in err and "'18650'" in err and "USB cable" in err


def test_dry_run_lists_the_parts_of_a_configuration(tmp_path, capsys):
    f = tmp_path / "gun.toml"
    f.write_text('[build]\nboard = "pi-zero-2w"\npower = "usb"\n')
    assert main(["build", str(f), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "pi-cm3_usb_filament-mx_minimal" in out
    assert "sled-pi-zero-2w" in out and "bulkhead-pi-camera" in out


def test_dry_run_all_lists_every_shipped_configuration(capsys):
    assert main(["build", "--all", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.count("board ") == 72


def test_list_names_every_shipped_configuration(capsys):
    import json

    assert main(["list", "--json"]) == 0
    names = json.loads(capsys.readouterr().out)
    assert len(names) == 72 and len(set(names)) == 72
    assert "pi-cm3_usb_filament-mx_minimal" in names
    assert "esp32-cam_18650_button-microswitch_blaster" in names


def test_build_one_shipped_configuration_by_name(capsys):
    name = "esp32-cam_aa_bolt-mx_blaster"
    assert main(["build", "--shipped", name, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"{name}:" in out and "trigger-lever-bolt" in out
    assert main(["build", "--shipped", "nope", "--dry-run"]) == 2
