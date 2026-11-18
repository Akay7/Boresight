"""The gun's configuration: one TOML file, with the server's defaults.

Calibration files are the ones the server writes, so a lens calibration or
a zero made there can be copied to the Pi. Each is a store keyed by client
and camera; `lens_key` and `zero_key` pick the entry, and a file with a
single entry needs no key.
"""

from __future__ import annotations

import json
import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from boresight.aim_hold import DEFAULT_HOLD_S
from boresight.lens import LensModel
from boresight.marker_map import MarkerMap, MarkerMapError, load_marker_map
from boresight.pipeline import DEFAULT_CONFIG_PATH as DEFAULT_LAYOUT_PATH
from boresight.zeroing import Zero

DEFAULT_CONFIG_PATH = Path("/etc/boresight-gun.toml")

logger = logging.getLogger(__name__)

# "usb": a USB absolute mouse for another machine (the HID gadget).
# "local": the display this computer drives, through the same overlay and
# uinput pointer the server uses.
OUTPUTS = ("usb", "local")


class ConfigError(ValueError):
    pass


CAMERA_SOURCES = ("auto", "webcam", "rpicam", "picamera2")


@dataclass(frozen=True)
class CameraConfig:
    # "auto": rpicam where `rpicam-vid` is installed, a webcam otherwise.
    # "webcam": any camera OpenCV opens (USB/V4L2). "rpicam": a Pi CSI
    # camera through the `rpicam-vid` program. "picamera2": a Pi CSI camera
    # through the OS's Picamera2 library (needs a venv that sees it).
    source: str = "auto"
    # A webcam's index or device path; for rpicam, the camera's index.
    device: int | str = 0
    width: int = 640
    height: int = 480
    fps: int = 30
    # Fixed, never automatic: auto-exposure chases the bright panel and
    # underexposes the paper markers.
    exposure_us: int = 4000
    gain: float = 1.0


@dataclass(frozen=True)
class PinsConfig:
    trigger: int = 17
    led: int | None = 27
    debounce_ms: int = 10


@dataclass(frozen=True)
class OverlayConfig:
    """The local output's on-screen markers: the server's overlay settings,
    meaning the same here."""

    # The display, by output name or index; None for the primary one.
    display: str | int | None = None
    extra_margin_px: int = 0
    # "4:3": tags in the bars beside a centred picture of that shape.
    picture_aspect: str | None = None


@dataclass(frozen=True)
class TuningConfig:
    smoothing: bool = True
    min_cutoff: float = 0.5
    beta: float = 1.0
    hold_s: float = DEFAULT_HOLD_S


@dataclass(frozen=True)
class GunConfig:
    # The reference layout shipped with the package, until a file names one.
    layout: Path = DEFAULT_LAYOUT_PATH
    lens_file: Path | None = None
    lens_key: str | None = None
    zero_file: Path | None = None
    zero_key: str | None = None
    hid_path: str = "/dev/hidg0"
    camera: CameraConfig = field(default_factory=CameraConfig)
    pins: PinsConfig = field(default_factory=PinsConfig)
    tuning: TuningConfig = field(default_factory=TuningConfig)
    output: str = "usb"
    overlay: OverlayConfig = field(default_factory=OverlayConfig)


SECTIONS = ("camera", "pins", "tuning", "overlay")


@dataclass(frozen=True)
class Loaded:
    """The config with every file it names read and checked."""

    config: GunConfig
    # None for the local output: its layout is the one the overlay draws,
    # known once the overlay reports its geometry.
    marker_map: MarkerMap | None
    lens: LensModel | None
    zero: Zero | None


def _section(data: dict, name: str, cls):
    raw = data.get(name, {})
    if not isinstance(raw, dict):
        raise ConfigError(f"[{name}] must be a table")
    allowed = set(cls.__dataclass_fields__)
    unknown = set(raw) - allowed
    if unknown:
        raise ConfigError(f"unknown key(s) in [{name}]: {', '.join(sorted(unknown))}")
    try:
        return cls(**raw)
    except TypeError as error:
        raise ConfigError(f"[{name}]: {error}") from error


def parse_config(data: dict) -> GunConfig:
    top = {key: value for key, value in data.items() if key not in SECTIONS}
    allowed = set(GunConfig.__dataclass_fields__) - set(SECTIONS)
    unknown = set(top) - allowed
    if unknown:
        raise ConfigError(f"unknown key(s): {', '.join(sorted(unknown))}")
    if top.get("output", "usb") not in OUTPUTS:
        raise ConfigError(
            f"output must be {' or '.join(repr(o) for o in OUTPUTS)}, "
            f"not {top['output']!r}"
        )
    for key in ("layout", "lens_file", "zero_file"):
        if key in top:
            top[key] = Path(top[key]) if top[key] else None
    try:
        config = GunConfig(
            **top,
            camera=_section(data, "camera", CameraConfig),
            pins=_section(data, "pins", PinsConfig),
            tuning=_section(data, "tuning", TuningConfig),
            overlay=_section(data, "overlay", OverlayConfig),
        )
    except TypeError as error:
        raise ConfigError(str(error)) from error
    overlay = config.overlay
    if not isinstance(overlay.extra_margin_px, int) or overlay.extra_margin_px < 0:
        raise ConfigError("[overlay] extra_margin_px must be a whole number, 0 or more")
    if overlay.picture_aspect:
        from boresight.overlay.layout import OverlayGeometryError, parse_picture_aspect

        try:
            parse_picture_aspect(overlay.picture_aspect)
        except OverlayGeometryError as error:
            raise ConfigError(f"[overlay] picture_aspect: {error}") from None
    camera = config.camera
    if camera.width < 1 or camera.height < 1 or camera.fps < 1:
        raise ConfigError("[camera] width, height and fps must be positive")
    if camera.source not in CAMERA_SOURCES:
        raise ConfigError(
            f"[camera] source must be one of {', '.join(CAMERA_SOURCES)}, "
            f"not {camera.source!r}"
        )
    if camera.source == "rpicam" and (problem := rpicam_size_problem(camera)):
        raise ConfigError(problem)
    if config.pins.debounce_ms < 1:
        raise ConfigError("[pins] debounce_ms must be at least 1")
    return config


def rpicam_size_problem(camera: CameraConfig) -> str | None:
    """Why `rpicam-vid` would pad frames of this size, or None.

    Its raw output is the camera buffer as is. Rows are padded unless the
    width is a multiple of 64, and the planes unless the height is a
    multiple of 16, and a reader expecting packed frames would drift.
    """
    if camera.width % 64 or camera.height % 16:
        return (
            f"[camera] {camera.width}x{camera.height} does not suit the rpicam "
            "source: the width must be a multiple of 64 and the height of 16 "
            "(e.g. 640x480, 1024x768, 1280x720)"
        )
    return None


def _pick(store: dict, key: str | None, what: str, path: Path) -> dict:
    if key is not None:
        if key not in store:
            raise ConfigError(f"{what} file {path} has no entry {key!r}")
        return store[key]
    if len(store) != 1:
        names = ", ".join(sorted(store)) or "none"
        raise ConfigError(
            f"{what} file {path} has {len(store)} entries ({names}); "
            f"set {what}_key to choose one"
        )
    return next(iter(store.values()))


def _read_json(path: Path, what: str) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ConfigError(f"cannot read {what} file {path}: {error}") from error
    if not isinstance(data, dict):
        raise ConfigError(f"{what} file {path} is not an object")
    return data


def load_lens(config: GunConfig) -> LensModel | None:
    if config.lens_file is None:
        return None
    store = _read_json(config.lens_file, "lens")
    try:
        return LensModel.from_dict(
            _pick(store, config.lens_key, "lens", config.lens_file)
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ConfigError(
            f"invalid lens calibration in {config.lens_file}: {error}"
        ) from error


def load_zero(config: GunConfig) -> Zero | None:
    if config.zero_file is None:
        return None
    clients = _read_json(config.zero_file, "zero").get("clients")
    if not isinstance(clients, dict):
        raise ConfigError(f"zero file {config.zero_file} has no 'clients' table")
    try:
        return Zero.from_dict(_pick(clients, config.zero_key, "zero", config.zero_file))
    except (TypeError, ValueError) as error:
        raise ConfigError(f"invalid zero in {config.zero_file}: {error}") from error


def load(path: Path | str | None = None, *, overrides: dict | None = None) -> Loaded:
    """Read the config file (defaults if `path` is None) and everything it
    names. Raises `ConfigError` with the reason."""
    data: dict = {}
    if path is not None:
        try:
            data = tomllib.loads(Path(path).read_text())
        except OSError as error:
            raise ConfigError(f"cannot read config {path}: {error}") from error
        except tomllib.TOMLDecodeError as error:
            raise ConfigError(f"config {path} is not valid TOML: {error}") from error
    if overrides:
        data = {**data, **overrides}
    config = parse_config(data)
    marker_map = None
    if config.output == "local":
        if "layout" in data:
            logger.info(
                "the local output solves against the overlay's own layout; "
                "layout %s is ignored",
                config.layout,
            )
    else:
        try:
            marker_map = load_marker_map(config.layout)
        except (OSError, MarkerMapError) as error:
            raise ConfigError(f"marker layout {config.layout}: {error}") from error
    lens = load_lens(config)
    if lens is not None:
        size = (config.camera.width, config.camera.height)
        if tuple(lens.image_size) != size:
            # The pipeline would drop it silently; at startup it is an error.
            raise ConfigError(
                f"lens calibration was made at {lens.image_size[0]}x"
                f"{lens.image_size[1]} but the camera is set to "
                f"{size[0]}x{size[1]}; a calibration is never rescaled"
            )
    return Loaded(config, marker_map, lens, load_zero(config))
