"""Which printed parts a configuration needs, by file name, without geometry.

The names here are the file names of the exported parts and the rows of
the print list, and the assembly builds exactly these parts (some, like
the barrels and the spacer collars, more than once).
"""

from __future__ import annotations

from collections import Counter

from boresight_case.config import Config

BONES = ("receiver", "barrel", "grip", "rear-cap")
# Each trigger mechanism's own printed parts. The switch plates are shared.
MECHANISM_PARTS = {
    "bolt": ("trigger-housing-bolt", "trigger-blade"),
    "button": ("trigger-housing-button", "button-plunger"),
}
KIT_PARTS = {
    "esp32-cam": ("nose-esp32-cam", "nose-sleeve"),
    "pi-zero-2w": ("camera-pi", "sled-pi-zero-2w", "pi-retainer", "cable-clamp"),
}
FEEDBACK_PARTS = {
    "none": (),
    "vibration": ("feedback-vibration",),
    "solenoid": ("feedback-solenoid", "solenoid-strap"),
    "lra": ("feedback-lra",),
}
# The runs on the receiver's rails, rear to front: (length, part) pairs
# after the hub on the left and from the rear cap on the right.
SPACER_LEFT = {
    False: ((34, "spacer-34"),),
    True: ((22, "button-panel"), (12, "spacer-12")),
}
SPACER_RIGHT = ((36, "spacer-36"),)
NO_FEEDBACK = (40, "spacer-40")
COLLAR = "spacer-collar"
SKIN_SECTIONS = ("barrel", "receiver", "grip")
SIDES = ("left", "right")
# Accent parts each style adds when its `accents` parameter is on.
STYLE_ACCENTS = {
    "minimal": (),
    "blaster": ("stripe-left", "stripe-right"),
}


def bolt_count(cfg: Config) -> int:
    """Through-bolts: two at each port, the grip's joint and backstrap."""
    ports = 2 + cfg.barrels
    return 2 * ports + 2


def skin_names(cfg: Config) -> list[str]:
    names = [
        f"skin-{cfg.style}-{section}-{side}"
        for section in SKIN_SECTIONS
        for side in SIDES
        if section != "barrel" or cfg.barrels > 0
    ]
    names.append(f"skin-{cfg.style}-muzzle")
    if cfg.style_params.get("accents", False):
        names += [f"accent-{cfg.style}-{a}" for a in STYLE_ACCENTS[cfg.style]]
    return names


def part_counts(cfg: Config, skins: bool = True) -> Counter:
    """Every printed part file of `cfg`, with how many to print."""
    c: Counter = Counter()
    for bone in BONES:
        c[bone] += cfg.barrels if bone == "barrel" else 1
    if c["barrel"] == 0:
        del c["barrel"]
    for name in MECHANISM_PARTS[cfg.mechanism]:
        c[name] += 1
    c[f"switch-plate-{cfg.trigger}"] += 1
    c[f"drawer-{cfg.power}"] += 1
    c["hub"] += 1
    for _, name in SPACER_LEFT[cfg.buttons]:
        c[name] += 1
    for _, name in SPACER_RIGHT:
        c[name] += 1
    if cfg.feedback == "none":
        c[NO_FEEDBACK[1]] += 1
    for name in FEEDBACK_PARTS[cfg.feedback]:
        c[name] += 1
    for name in KIT_PARTS[cfg.board]:
        c[name] += 1
    if skins:
        for name in skin_names(cfg):
            c[name] += cfg.barrels if "-barrel-" in name else 1
    else:
        c[COLLAR] += 2 * bolt_count(cfg)
    return c


def part_names(cfg: Config, skins: bool = True) -> list[str]:
    """Every printed part file of `cfg`, once each, in assembly order."""
    return list(part_counts(cfg, skins))
