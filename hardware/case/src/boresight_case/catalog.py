"""Which printed parts a configuration needs, by name, without geometry.

The names here are the file names of the exported parts and the rows of
the print list, and the assembly builds exactly these parts.
"""

from __future__ import annotations

from boresight_case.config import Config

CORE_PARTS = ("receiver", "barrel", "grip", "rear-cap")
# Each trigger mechanism's own printed parts. The switch plates are shared.
MECHANISM_PARTS = {
    "filament": ("trigger-cassette-filament", "trigger-lever-filament"),
    "bolt": ("trigger-cassette-bolt", "trigger-lever-bolt"),
    "button": ("button-cassette", "button-plunger", "button-cap"),
}
SKIN_SECTIONS = ("barrel", "receiver", "grip")
SIDES = ("left", "right")
# Accent parts each style adds when its `accents` parameter is on.
STYLE_ACCENTS = {
    "minimal": (),
    "blaster": ("stripe-left", "stripe-right", "muzzle-ring"),
}


def bulkhead_name(cfg: Config) -> str:
    return "bulkhead-esp32-cam" if cfg.board == "esp32-cam" else "bulkhead-pi-camera"


def skin_names(cfg: Config) -> list[str]:
    names = [
        f"skin-{cfg.style}-{section}-{side}"
        for section in SKIN_SECTIONS
        for side in SIDES
    ]
    if cfg.style_params.get("accents", False):
        names += [f"accent-{cfg.style}-{a}" for a in STYLE_ACCENTS[cfg.style]]
    return names


def part_names(cfg: Config) -> list[str]:
    """Every printed part of `cfg`, in assembly order."""
    names = list(CORE_PARTS)
    names += MECHANISM_PARTS[cfg.mechanism]
    names.append(f"switch-plate-{cfg.trigger}")
    names.append(bulkhead_name(cfg))
    if cfg.board == "pi-zero-2w":
        names.append("sled-pi-zero-2w")
    names.append(f"drawer-{cfg.power}")
    names += skin_names(cfg)
    return names
