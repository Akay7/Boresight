"""A case configuration: which kit, drawer, switch and style, and the printer.

One TOML file, like the repository's other settings files:

    [build]
    board = "esp32-cam"        # or "pi-zero-2w"
    power = "aa"               # "aaa", "18650", "usb"
    trigger = "mx"             # or "microswitch"
    mechanism = "filament"     # lever on a filament pin; "bolt" or "button"
    style = "blaster"          # or "minimal"
    camera = "cm3"             # Pi kit only: "cm2" or "cm3"

    [style]                    # style parameters, each range-checked
    shroud_length = 20

    [printer]
    volume = [180, 180, 180]
    clearance = 0.25
    interference = 0.05
    fastener = "nut"           # or "insert"

Every key is optional. Validity is checked here, before any geometry is
built, so a configuration that cannot be assembled never reaches the CAD
kernel.
"""

from __future__ import annotations

import itertools
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from boresight_case.styles import STYLES, StyleParamError, resolve_style_params

BOARDS = ("esp32-cam", "pi-zero-2w")
POWERS = ("aa", "aaa", "18650", "usb")
TRIGGERS = ("mx", "microswitch")
# How the trigger moves: a lever on a 1.75 mm filament pin, the same lever
# on an M3 bolt, or a push button pressed straight back.
MECHANISMS = ("filament", "bolt", "button")
# The camera each board kit carries. The ESP32-CAM's OV2640 is part of the
# board; the Pi kit takes either Camera Module on the same pegs.
CAMERAS = {"esp32-cam": ("ov2640",), "pi-zero-2w": ("cm2", "cm3")}
DEFAULT_CAMERA = {"esp32-cam": "ov2640", "pi-zero-2w": "cm3"}
FASTENERS = ("nut", "insert")

# The Pi takes its power and its data through the one USB cable to the
# host, so it has no use for cells: only the tether drawer fits it.
VALID_POWERS = {"esp32-cam": POWERS, "pi-zero-2w": ("usb",)}


class ConfigError(ValueError):
    pass


class Params(Mapping[str, Any]):
    """Style parameters: a read-only, hashable mapping, so a Config can key
    the caches that hold its built geometry."""

    def __init__(self, items: Mapping[str, Any]) -> None:
        self._items = tuple(sorted(items.items()))
        self._dict = dict(self._items)

    def __getitem__(self, key: str) -> Any:
        return self._dict[key]

    def __iter__(self):
        return iter(self._dict)

    def __len__(self) -> int:
        return len(self._dict)

    def __hash__(self) -> int:
        return hash(self._items)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Mapping) and dict(self._items) == dict(other)

    def __repr__(self) -> str:
        return f"Params({self._dict!r})"


@dataclass(frozen=True)
class Printer:
    volume: tuple[float, float, float] = (180.0, 180.0, 180.0)
    # Every sliding, clip and peg fit opens by this much per side; tune it
    # with the fit coupon.
    clearance: float = 0.25
    # Every press fit (nut traps, magnets of a remix) closes by this much.
    interference: float = 0.05
    fastener: str = "nut"


@dataclass(frozen=True)
class Config:
    board: str = "esp32-cam"
    power: str = "aa"
    trigger: str = "mx"
    mechanism: str = "filament"
    style: str = "minimal"
    camera: str = ""
    style_params: Mapping[str, Any] = field(default_factory=dict)
    printer: Printer = Printer()

    def __post_init__(self) -> None:
        _check_choice("board", self.board, BOARDS)
        _check_choice("power", self.power, POWERS)
        _check_choice("trigger", self.trigger, TRIGGERS)
        _check_choice("mechanism", self.mechanism, MECHANISMS)
        _check_choice("style", self.style, STYLES)
        if self.power not in VALID_POWERS[self.board]:
            raise ConfigError(
                f"board {self.board!r} cannot use power drawer {self.power!r}: "
                "the Pi takes its power and its data from the one USB cable "
                "to the host, so only the 'usb' tether drawer fits it"
            )
        if not self.camera:
            object.__setattr__(self, "camera", DEFAULT_CAMERA[self.board])
        elif self.board == "esp32-cam" and self.camera != "ov2640":
            raise ConfigError(
                "camera is chosen only for the Pi kit; the ESP32-CAM's "
                f"OV2640 is part of the board (got camera {self.camera!r})"
            )
        else:
            _check_choice("camera", self.camera, CAMERAS[self.board])
        try:
            resolved = resolve_style_params(self.style, self.style_params)
        except StyleParamError as e:
            raise ConfigError(str(e)) from None
        object.__setattr__(self, "style_params", Params(resolved))
        _check_printer(self.printer)

    @property
    def name(self) -> str:
        """A stable directory name for this configuration's outputs."""
        board = self.board if self.board == "esp32-cam" else f"pi-{self.camera}"
        return f"{board}_{self.power}_{self.mechanism}-{self.trigger}_{self.style}"


def _check_choice(key: str, value: Any, choices: tuple[str, ...]) -> None:
    if value not in choices:
        raise ConfigError(
            f"{key} must be one of {', '.join(repr(c) for c in choices)}, not {value!r}"
        )


def _check_printer(p: Printer) -> None:
    if len(p.volume) != 3 or any(v <= 0 for v in p.volume):
        raise ConfigError(
            f"printer volume must be three positive sizes in mm, not {p.volume!r}"
        )
    if not 0.0 <= p.clearance <= 1.0:
        raise ConfigError(f"printer clearance must be 0 to 1 mm, not {p.clearance!r}")
    if not 0.0 <= p.interference <= 0.5:
        raise ConfigError(
            f"printer interference must be 0 to 0.5 mm, not {p.interference!r}"
        )
    _check_choice("printer fastener", p.fastener, FASTENERS)


_SECTIONS = {"build", "style", "printer"}
_BUILD_KEYS = {"board", "power", "trigger", "mechanism", "style", "camera"}
_PRINTER_KEYS = {"volume", "clearance", "interference", "fastener"}


def from_dict(data: Mapping[str, Any]) -> Config:
    """A Config from parsed TOML, refusing unknown sections and keys."""
    _no_unknown("section", data, _SECTIONS)
    build = data.get("build", {})
    printer = data.get("printer", {})
    _no_unknown("[build] key", build, _BUILD_KEYS)
    _no_unknown("[printer] key", printer, _PRINTER_KEYS)
    try:
        p = Printer(
            volume=tuple(float(v) for v in printer.get("volume", Printer.volume)),
            clearance=float(printer.get("clearance", Printer.clearance)),
            interference=float(printer.get("interference", Printer.interference)),
            fastener=printer.get("fastener", Printer.fastener),
        )
    except (TypeError, ValueError) as e:
        raise ConfigError(f"[printer]: {e}") from None
    return Config(
        board=build.get("board", Config.board),
        power=build.get("power", Config.power),
        trigger=build.get("trigger", Config.trigger),
        mechanism=build.get("mechanism", Config.mechanism),
        style=build.get("style", Config.style),
        camera=build.get("camera", ""),
        style_params=dict(data.get("style", {})),
        printer=p,
    )


def _no_unknown(what: str, given: Mapping[str, Any], known: set[str]) -> None:
    if not isinstance(given, Mapping):
        raise ConfigError(f"{what.split()[0]} must be a table")
    unknown = sorted(set(given) - known)
    if unknown:
        raise ConfigError(
            f"unknown {what} {unknown[0]!r}; expected one of {', '.join(sorted(known))}"
        )


def load(path: Path) -> Config:
    try:
        data = tomllib.loads(path.read_text())
    except OSError as e:
        raise ConfigError(f"cannot read {path}: {e.strerror}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path} is not valid TOML: {e}") from None
    return from_dict(data)


def shipped_configurations(printer: Printer | None = None) -> list[Config]:
    """Every valid combination of the shipped kits, drawers, switches and
    styles, with default style parameters."""
    printer = printer or Printer()
    configs = []
    combos = itertools.product(BOARDS, MECHANISMS, TRIGGERS, STYLES)
    for board, mechanism, trigger, style in combos:
        for power, camera in itertools.product(VALID_POWERS[board], CAMERAS[board]):
            configs.append(
                Config(
                    board=board,
                    power=power,
                    trigger=trigger,
                    mechanism=mechanism,
                    style=style,
                    camera=camera,
                    printer=printer,
                )
            )
    return configs
