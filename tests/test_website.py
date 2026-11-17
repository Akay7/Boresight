"""The project site's build hook and the flasher's firmware bundle.

`website/hooks.py` and `website/flasher.py` are scripts MkDocs loads by
path, not parts of the package, so they are loaded the same way here.
Nothing in this module needs MkDocs installed; `mkdocs build --strict`
itself runs in CI (.github/workflows/site.yml).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boresight.inject import FakeCursorBackend
from boresight.server import create_app

REPO = Path(__file__).parents[1]
WEBSITE = REPO / "website"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, WEBSITE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


flasher = _load("flasher")
hooks = _load("hooks")

FLASH_ARGS = """--flash_mode dio --flash_freq 40m --flash_size 4MB
0x1000 bootloader/bootloader.bin
0x20000 boresight-cam.bin
0x8000 partition_table/partition-table.bin
0xf000 ota_data_initial.bin
"""


def _app_image(version: str = "0.2.0") -> bytes:
    """The head of an application image: header, segment header, then the
    app descriptor with its version, project, time and date fields."""
    head = bytearray(256)
    head[0] = 0xE9
    head[32:36] = (0xABCD5432).to_bytes(4, "little")
    head[48 : 48 + len(version)] = version.encode()
    head[80:93] = b"boresight-cam"
    head[112:120] = b"17:42:05"
    head[128:139] = b"Nov 17 2026"
    return bytes(head) + b"\x00" * 1024


@pytest.fixture
def build(tmp_path: Path) -> Path:
    root = tmp_path / "build"
    (root / "bootloader").mkdir(parents=True)
    (root / "partition_table").mkdir()
    (root / "flash_args").write_text(FLASH_ARGS)
    (root / "bootloader" / "bootloader.bin").write_bytes(b"BOOT" * 16)
    (root / "partition_table" / "partition-table.bin").write_bytes(b"PART" * 16)
    (root / "ota_data_initial.bin").write_bytes(b"\xff" * 8192)
    (root / "boresight-cam.bin").write_bytes(_app_image())
    return root


# --- The firmware bundle ----------------------------------------------------


def test_the_bundle_writes_the_four_parts_at_their_offsets(
    build: Path, tmp_path: Path
) -> None:
    out = tmp_path / "flash"
    manifest = flasher.write_bundle(build, out)

    assert manifest == json.loads((out / "manifest.json").read_text())
    assert manifest["version"] == "0.2.0"
    assert manifest["built"] == "Nov 17 2026 17:42:05"
    [target] = manifest["builds"]
    assert target["chipFamily"] == "ESP32"
    assert target["parts"] == [
        {"path": "files/bootloader.bin", "offset": 0x1000},
        {"path": "files/partition-table.bin", "offset": 0x8000},
        # Without it, a board updated over Wi-Fi keeps booting its old slot.
        {"path": "files/ota_data_initial.bin", "offset": 0xF000},
        {"path": "files/boresight-cam.bin", "offset": 0x20000},
    ]
    # Nothing at NVS (0x9000-0xEFFF): the stored settings are not written.
    assert not any(0x9000 <= part["offset"] < 0xF000 for part in target["parts"])
    # Erasing is the user's choice, and Wi-Fi is set up in setup mode.
    assert manifest["new_install_prompt_erase"] is True
    assert manifest["new_install_improv_wait_time"] == 0
    for part in target["parts"]:
        assert (out / part["path"]).is_file()


def test_a_build_missing_a_part_is_not_bundled(build: Path, tmp_path: Path) -> None:
    (build / "ota_data_initial.bin").unlink()
    assert flasher.write_bundle(build, tmp_path / "flash") is None
    assert flasher.write_bundle(tmp_path / "nothing", tmp_path / "flash") is None


def test_a_release_bundle_is_copied_as_it_is(build: Path, tmp_path: Path) -> None:
    """A Release's assets, downloaded flat: the files beside the manifest."""
    made = tmp_path / "made"
    original = flasher.write_bundle(build, made)
    release = tmp_path / "release"
    release.mkdir()
    (release / "manifest.json").write_text((made / "manifest.json").read_text())
    for part in (made / "files").iterdir():
        (release / part.name).write_bytes(part.read_bytes())

    out = tmp_path / "flash"
    assert flasher.write_bundle(release, out) == original
    assert (out / "files" / "boresight-cam.bin").read_bytes() == _app_image()


def test_the_bundler_runs_on_its_own(build: Path, tmp_path: Path, capsys) -> None:
    assert flasher.main([str(build), str(tmp_path / "out")]) == 0
    assert "Boresight camera 0.2.0" in capsys.readouterr().out
    assert flasher.main([str(tmp_path / "nothing"), str(tmp_path / "out")]) == 1


# --- Rewriting the READMEs' links -------------------------------------------

SOURCE = "README.md"


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        # Another README: its page, anchor kept.
        ("firmware/boresight-cam/README.md", "firmware.md"),
        ("deploy/pi/README.md#install", "pi-gun.md#install"),
        # A source file and a directory: on GitHub.
        (
            "src/boresight/server.py",
            "https://github.com/Akay7/Boresight/blob/main/src/boresight/server.py",
        ),
        (
            "firmware/boresight-cam/main",
            "https://github.com/Akay7/Boresight/tree/main/firmware/boresight-cam/main",
        ),
        # Left alone: URLs, anchors on the page, and what does not exist,
        # which --strict then refuses.
        ("https://example.com/x", "https://example.com/x"),
        ("#the-esp32-cam-client", "#the-esp32-cam-client"),
        ("no/such/file.md", "no/such/file.md"),
    ],
)
def test_links_are_rewritten_for_the_site(
    target: str, expected: str, tmp_path: Path
) -> None:
    assert hooks.rewrite_target(target, SOURCE, tmp_path) == expected


def test_a_link_relative_to_a_nested_readme_resolves_from_it(tmp_path: Path) -> None:
    source = "firmware/boresight-cam/README.md"
    assert hooks.rewrite_target("../../README.md", source, tmp_path) == "index.md"
    assert hooks.rewrite_target("main/ota.c", source, tmp_path) == (
        "https://github.com/Akay7/Boresight/blob/main/firmware/boresight-cam/main/ota.c"
    )


def test_an_image_is_copied_and_shown_from_the_site(tmp_path: Path) -> None:
    image = "firmware/boresight-cam/docs/flashing.svg"

    assert hooks.rewrite_target(image, SOURCE, tmp_path) == f"assets/{image}"
    assert (tmp_path / "assets" / image).read_bytes() == (REPO / image).read_bytes()


def test_code_is_left_alone(tmp_path: Path) -> None:
    text = (
        "See [the firmware](firmware/boresight-cam/README.md).\n"
        "```\n[not a link](src/boresight/server.py)\n```\n"
        "    [indented code](src/boresight/server.py)\n"
    )
    rewritten = hooks.rewrite_page(text, SOURCE, tmp_path)

    assert "[the firmware](firmware.md)" in rewritten
    assert "[not a link](src/boresight/server.py)" in rewritten
    assert "    [indented code](src/boresight/server.py)" in rewritten


@pytest.fixture
def vendor(tmp_path: Path) -> Path:
    """Stands in for the fetched ESP Web Tools: nothing here downloads."""
    root = tmp_path / "vendor"
    (root / "esp-web-tools").mkdir(parents=True)
    (root / "esp-web-tools" / "install-button.js").write_text("export {};\n")
    return root


def _no_fetch() -> None:
    raise AssertionError("fetched although ESP Web Tools was there")


def test_the_site_is_assembled_with_the_flasher_and_a_build(
    build: Path, vendor: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("BORESIGHT_FIRMWARE", str(build))
    docs = tmp_path / "docs"

    hooks.assemble(docs, vendor, _no_fetch)

    for page in ("index.md", "firmware.md", "case.md", "pi-gun.md"):
        assert (docs / page).is_file()
    assert (docs / "flash" / "index.html").is_file()
    assert (docs / "vendor" / "esp-web-tools" / "install-button.js").is_file()
    manifest = json.loads((docs / "flash" / "manifest.json").read_text())
    assert manifest["version"] == "0.2.0"


def test_reassembling_writes_nothing_unchanged(
    build: Path, vendor: Path, tmp_path: Path, monkeypatch
) -> None:
    """`mkdocs serve` rebuilds when the docs change: a rebuild that rewrote
    them would never stop."""
    monkeypatch.setenv("BORESIGHT_FIRMWARE", str(build))
    docs = tmp_path / "docs"
    hooks.assemble(docs, vendor, _no_fetch)
    before = {path: path.stat().st_mtime_ns for path in docs.rglob("*")}

    hooks.assemble(docs, vendor, _no_fetch)

    assert {path: path.stat().st_mtime_ns for path in docs.rglob("*")} == before


def test_esp_web_tools_is_fetched_only_when_missing(tmp_path: Path) -> None:
    fetched = []
    missing = tmp_path / "vendor"

    hooks.ensure_vendor(missing, lambda: fetched.append(True))
    assert fetched == [True]

    (missing / "esp-web-tools").mkdir(parents=True)
    (missing / "esp-web-tools" / "install-button.js").write_text("")
    hooks.ensure_vendor(missing, _no_fetch)


def test_esp_web_tools_is_not_committed() -> None:
    """Fetched at its pinned hash by the site build instead (see
    tools/vendor-esp-web-tools.sh)."""
    tracked = subprocess.run(
        ["git", "ls-files", "website/vendor"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert tracked.stdout == ""
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "website/vendor/esp-web-tools/x.js"], cwd=REPO
    )
    assert ignored.returncode == 0


# --- The Boresight server keeps out of it ------------------------------------


def test_the_boresight_server_does_not_flash() -> None:
    with TestClient(create_app(backend_factory=FakeCursorBackend)) as client:
        for path in (
            "/flash/",
            "/flash/manifest.json",
            "/flash/files/boresight-cam.bin",
        ):
            assert client.get(path).status_code == 404
        assert client.get("/vendor/esp-web-tools/install-button.js").status_code == 404
