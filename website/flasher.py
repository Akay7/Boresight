"""A firmware bundle for the site's flashing page: `manifest.json` plus `files/`.

The flashing page (`flash/index.html`) flashes an ESP32-CAM from the
browser with ESP Web Tools over Web Serial. What it writes is described
by ESP Web Tools' manifest beside it, made here from a firmware build's
`flash_args`: the bootloader, the partition table, `ota_data_initial.bin`
(which points the board back at its first firmware slot -- without it, a
board that had updated over Wi-Fi would keep booting its old firmware
after a reflash) and the app, each at its offset. Those four and nothing
else: none of them touch NVS, so settings stored on the device survive.

Plain Python with no Boresight imports: the site build (`hooks.py`) and
CI use it, and it runs on its own:

    python website/flasher.py firmware/boresight-cam/build out/flash
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "boresight-cam.bin"
MANIFEST = "manifest.json"
# esp_app_desc_t inside an application image (offset 32): version,
# project name, then compile time and date, each a fixed-size field.
_DESC = 32
_VERSION = slice(_DESC + 16, _DESC + 48)
_TIME = slice(_DESC + 80, _DESC + 96)
_DATE = slice(_DESC + 96, _DESC + 112)


@dataclass(frozen=True)
class Part:
    name: str
    path: Path
    offset: int


def _field(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("ascii", errors="replace")


def read_parts(build_dir: Path) -> list[Part] | None:
    """What `idf.py flash` would write, from `flash_args`; None without a
    complete build. The first line is esptool options; each other is
    `offset path`."""
    flash_args = build_dir / "flash_args"
    if not flash_args.is_file():
        return None
    parts = []
    for line in flash_args.read_text().splitlines()[1:]:
        if not line.strip():
            continue
        offset, relative = line.split()
        path = build_dir / relative
        parts.append(Part(name=path.name, path=path, offset=int(offset, 16)))
    if not parts or not all(part.path.is_file() for part in parts):
        return None
    return sorted(parts, key=lambda part: part.offset)


def app_description(app: Path) -> dict[str, str]:
    head = app.read_bytes()[: _DATE.stop]
    return {
        "version": _field(head[_VERSION]),
        "built": f"{_field(head[_DATE])} {_field(head[_TIME])}".strip(),
    }


def manifest(parts: list[Part]) -> dict:
    app = next((part for part in parts if part.name == APP_NAME), None)
    description = app_description(app.path) if app is not None else {}
    return {
        "name": "Boresight camera",
        "version": description.get("version", "unknown"),
        # Read by the page, ignored by ESP Web Tools.
        "built": description.get("built", ""),
        # Erasing also erases the settings stored on the device, so it is
        # asked, not assumed.
        "new_install_prompt_erase": True,
        # No Improv: Wi-Fi is set up in the device's own setup mode.
        "new_install_improv_wait_time": 0,
        "builds": [
            {
                "chipFamily": "ESP32",
                "parts": [
                    {"path": f"files/{part.name}", "offset": part.offset}
                    for part in parts
                ],
            }
        ],
    }


def write_bundle(source: Path, out_dir: Path) -> dict | None:
    """The bundle for `source` in `out_dir`; None when there is nothing to
    bundle.

    `source` is a firmware build (with `flash_args`) or a bundle already
    made -- a release's, say (with `manifest.json`), which is copied.
    """
    if (source / MANIFEST).is_file():
        data = json.loads((source / MANIFEST).read_text())
        files = out_dir / "files"
        files.mkdir(parents=True, exist_ok=True)
        for part in data["builds"][0]["parts"]:
            name = Path(part["path"]).name
            found = source / "files" / name
            shutil.copy2(found if found.is_file() else source / name, files / name)
        (out_dir / MANIFEST).write_text(json.dumps(data, indent=2) + "\n")
        return data
    parts = read_parts(source)
    if parts is None:
        return None
    files = out_dir / "files"
    files.mkdir(parents=True, exist_ok=True)
    for part in parts:
        shutil.copy2(part.path, files / part.name)
    data = manifest(parts)
    (out_dir / MANIFEST).write_text(json.dumps(data, indent=2) + "\n")
    return data


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(
            "usage: python website/flasher.py BUILD_OR_BUNDLE OUT_DIR",
            file=sys.stderr,
        )
        return 2
    data = write_bundle(Path(args[0]), Path(args[1]))
    if data is None:
        print(f"no complete firmware build in {args[0]}", file=sys.stderr)
        return 1
    print(f"{data['name']} {data['version']} bundled in {args[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
