"""The gun's configuration: one TOML file, with the server's defaults.

Calibration files are the ones the server writes, so a lens calibration or
a zero made there can be copied to the Pi. Each is a store keyed by client
and camera; `lens_key` and `zero_key` pick the entry, and a file with a
single entry needs no key.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from boresight.aim_hold import DEFAULT_HOLD_S
from boresight.lens import LensModel
from boresight.marker_map import MarkerMap, MarkerMapError, load_marker_map
from boresight.pipeline import DEFAULT_CONFIG_PATH as DEFAULT_LAYOUT_PATH
from boresight.zeroing import Zero

DEFAULT_CONFIG_PATH = Path("/etc/boresight-gun.toml")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CameraConfig:
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


@dataclass(frozen=True)
class Loaded:
    """The config with every file it names read and checked."""

    config: GunConfig
    marker_map: MarkerMap
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
    top = {
        key: value
        for key, value in data.items()
        if key not in ("camera", "pins", "tuning")
    }
    allowed = set(GunConfig.__dataclass_fields__) - {"camera", "pins", "tuning"}
    unknown = set(top) - allowed
    if unknown:
        raise ConfigError(f"unknown key(s): {', '.join(sorted(unknown))}")
    for key in ("layout", "lens_file", "zero_file"):
        if key in top:
            top[key] = Path(top[key]) if top[key] else None
    try:
        config = GunConfig(
            **top,
            camera=_section(data, "camera", CameraConfig),
            pins=_section(data, "pins", PinsConfig),
            tuning=_section(data, "tuning", TuningConfig),
        )
    except TypeError as error:
        raise ConfigError(str(error)) from error
    camera = config.camera
    if camera.width < 1 or camera.height < 1 or camera.fps < 1:
        raise ConfigError("[camera] width, height and fps must be positive")
    if config.pins.debounce_ms < 1:
        raise ConfigError("[pins] debounce_ms must be at least 1")
    return config


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
