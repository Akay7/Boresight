"""Runtime settings: what they are, where they come from, and saving them.

Every setting the server takes, one table per concern, each range-checked
by one pydantic model, so a value is validated the same way whether it
came from the settings file, an environment variable, a command-line
flag or the phone:

- `[server]`, `[markers]`, `[detection]` and `[recording]` are read at
  startup only: the address, token and TLS, the marker layout, the
  tracker's thresholds and the recording window. Edited by hand.

- `[tuning]` shapes how aim feels: the one-euro filter's `min_cutoff`
  and `beta` (`one_euro.py`), the dropout hold window (`aim_hold.py`)
  and the relative-motion scale (`inject.py`). All tuned by feel, which
  is why they can be changed while the server runs.
- `[view]` is what the phone would otherwise lose on a restart: the
  debug overlay default, the marker source, the overlay margin and the
  display the gun aims at.

Each value is resolved once, at startup, in decreasing precedence:
command-line flag, environment variable, settings file, built-in
default. After that the API is the only live path (`LiveSettings`);
the file is read at startup and written on save, never watched.

The file lives under `.boresight/` by default, next to the generated
certificate. Tables this module does not know are ignored on load and
written back untouched on save, so other per-machine state can share
the file; the file helpers at the bottom are generic for the same
reason.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import tempfile
import threading
import tomllib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from boresight.detect import (
    COARSE_BACKOFF_FRAMES,
    COARSE_MIN_SIDE_PX,
    FULL_PASS_EVERY_FRAMES,
    TrackerOptions,
)
from boresight.layout_source import DEFAULT_SPEC
from boresight.netaccess import DEFAULT_HOST, DEFAULT_PORT
from boresight.recording import DEFAULT_RECORD_MAX_BYTES, DEFAULT_RECORD_SECONDS

STATE_DIR = Path(".boresight")
DEFAULT_SETTINGS_PATH = STATE_DIR / "config.toml"

# name -> (minimum, maximum, default). The one place each range is
# written down: the model, the update request and `GET /settings` all
# read it from here, so they cannot drift apart.
TUNING_RANGES: dict[str, tuple[float, float, float]] = {
    # Hz. Below ~0.01 a held aim takes minutes to settle; above 10 the
    # filter barely smooths at camera frame rates.
    "min_cutoff": (0.01, 10.0, 0.5),
    # Cutoff added per unit of speed (screen widths per second).
    "beta": (0.0, 10.0, 1.0),
    # Seconds. Zero disables holding.
    "hold_s": (0.0, 5.0, 0.75),
    # Device-motion units per full-screen sweep. Zero is off; see
    # `inject.DEFAULT_REL_SCALE` for why it stays off by default.
    "rel_scale": (0.0, 10000.0, 0.0),
}
OVERLAY_MARGIN_MAX_PX = 2000


def _tuning_field(name: str):
    minimum, maximum, default = TUNING_RANGES[name]
    return Field(default, ge=minimum, le=maximum)


class Tuning(BaseModel):
    # Strict: `debug = "yes"` or `beta = "2"` in the file is a mistake
    # to report, not something to coerce.
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    min_cutoff: float = _tuning_field("min_cutoff")
    beta: float = _tuning_field("beta")
    hold_s: float = _tuning_field("hold_s")
    rel_scale: float = _tuning_field("rel_scale")


class TuningUpdate(BaseModel):
    """A partial change to `Tuning`: only the fields present change."""

    model_config = ConfigDict(extra="forbid")

    min_cutoff: float | None = Field(
        None, ge=TUNING_RANGES["min_cutoff"][0], le=TUNING_RANGES["min_cutoff"][1]
    )
    beta: float | None = Field(
        None, ge=TUNING_RANGES["beta"][0], le=TUNING_RANGES["beta"][1]
    )
    hold_s: float | None = Field(
        None, ge=TUNING_RANGES["hold_s"][0], le=TUNING_RANGES["hold_s"][1]
    )
    rel_scale: float | None = Field(
        None, ge=TUNING_RANGES["rel_scale"][0], le=TUNING_RANGES["rel_scale"][1]
    )


class ViewPreferences(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    debug: bool = False
    marker_source: Literal["printed", "screen"] = "printed"
    overlay_extra_margin_px: int = Field(0, ge=0, le=OVERLAY_MARGIN_MAX_PX)
    # The display the gun aims at, by output name; empty for the
    # primary display (`displays.py`).
    display: str = Field("", max_length=128)


class ServerOptions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    host: str = DEFAULT_HOST
    port: int = Field(DEFAULT_PORT, ge=1, le=65535)
    # A secret, like the TLS key beside this file in `.boresight/`.
    token: str | None = Field(None, min_length=1)
    token_auto: bool = False
    tls: bool = False
    # Paths as written; relative ones resolve against the working
    # directory, as they would on the command line.
    certfile: str | None = None
    keyfile: str | None = None
    qr: bool = True


class MarkerOptions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    # 'file', 'file:<path>' or 'screen:<W>x<H>' (`layout_source.py`).
    layout: str = DEFAULT_SPEC


class DetectionOptions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    # Off: every frame gets the full-resolution search.
    tracked: bool = True
    coarse_min_side_px: float = Field(COARSE_MIN_SIDE_PX, ge=1.0, le=10000.0)
    full_pass_every: int = Field(FULL_PASS_EVERY_FRAMES, ge=1, le=10000)
    backoff_frames: int = Field(COARSE_BACKOFF_FRAMES, ge=0, le=10000)

    def tracker(self) -> TrackerOptions | None:
        if not self.tracked:
            return None
        return TrackerOptions(
            min_side_px=self.coarse_min_side_px,
            full_pass_every=self.full_pass_every,
            backoff_frames=self.backoff_frames,
        )


class RecordingOptions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    # Zero disables recording.
    seconds: float = Field(DEFAULT_RECORD_SECONDS, ge=0.0, le=3600.0)
    max_mb: float = Field(DEFAULT_RECORD_MAX_BYTES / (1024 * 1024), ge=0.0, le=65536.0)


class Settings(BaseModel):
    # Unknown top-level tables are someone else's.
    model_config = ConfigDict(frozen=True, extra="ignore")

    server: ServerOptions = Field(default_factory=ServerOptions)
    markers: MarkerOptions = Field(default_factory=MarkerOptions)
    detection: DetectionOptions = Field(default_factory=DetectionOptions)
    recording: RecordingOptions = Field(default_factory=RecordingOptions)
    tuning: Tuning = Field(default_factory=Tuning)
    view: ViewPreferences = Field(default_factory=ViewPreferences)


# Where a value can be pinned from, by dotted key. Only the tuning
# values ever had environment variables; every setting that was a
# command-line option still is one.
ENV_VARS: dict[str, str] = {
    "tuning.min_cutoff": "BORESIGHT_AIM_MIN_CUTOFF",
    "tuning.beta": "BORESIGHT_AIM_BETA",
    "tuning.hold_s": "BORESIGHT_AIM_HOLD_S",
    "tuning.rel_scale": "BORESIGHT_REL_SCALE",
}
CLI_FLAGS: dict[str, str] = {
    "tuning.min_cutoff": "--aim-min-cutoff",
    "tuning.beta": "--aim-beta",
    "tuning.hold_s": "--aim-hold-s",
    "tuning.rel_scale": "--rel-scale",
    "view.overlay_extra_margin_px": "--overlay-extra-margin-px",
    "view.display": "--display",
    "server.host": "--host",
    "server.port": "--port",
    "server.token": "--token",
    "server.token_auto": "--token-auto",
    "server.tls": "--tls",
    "server.certfile": "--certfile",
    "server.keyfile": "--keyfile",
    "server.qr": "--qr",
    "markers.layout": "--markers",
    "detection.tracked": "--tracked-detection",
    "recording.seconds": "--record-seconds",
    "recording.max_mb": "--record-max-mb",
}


class SettingsError(ValueError):
    """A setting that cannot be used, with where it came from."""


def tuning_limits() -> dict[str, dict[str, float]]:
    return {
        name: {"min": minimum, "max": maximum, "default": default}
        for name, (minimum, maximum, default) in TUNING_RANGES.items()
    }


def _describe(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
        for item in error.errors()
    )


def _with(data: dict, key: str, value: object) -> dict:
    """`data` with the dotted `key` set, copied rather than mutated."""
    table, name = key.split(".")
    return {**data, table: {**data.get(table, {}), name: value}}


def resolve_settings(
    path: Path | None = DEFAULT_SETTINGS_PATH,
    env: Mapping[str, str] | None = None,
    cli: Mapping[str, object | None] | None = None,
) -> LiveSettings:
    """Settings from, in increasing precedence: defaults, the file at
    `path`, `env`, then `cli` (dotted key -> value, None = not given).

    Each layer is validated as it is applied, so the error names the
    place the bad value came from rather than just the key.
    """
    env = os.environ if env is None else env
    cli = cli or {}

    file_data: dict = {}
    if path is not None and path.is_file():
        try:
            file_data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            raise SettingsError(f"settings file {path}: {error}") from error
    data = {
        table: file_data[table] for table in Settings.model_fields if table in file_data
    }
    for table, value in data.items():
        if not isinstance(value, dict):
            raise SettingsError(f"settings file {path}: [{table}] must be a table")
    try:
        Settings.model_validate(data)
    except ValidationError as error:
        raise SettingsError(f"settings file {path}: {_describe(error)}") from error

    pinned: dict[str, str] = {}
    for key, variable in ENV_VARS.items():
        raw = env.get(variable)
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            raise SettingsError(f"{variable}={raw!r} is not a number") from None
        data = _checked(_with(data, key, value), f"{variable}={raw!r}")
        pinned[key] = variable

    for key, value in cli.items():
        if value is None:
            continue
        flag = CLI_FLAGS.get(key, key)
        data = _checked(_with(data, key, value), f"{flag} {value}")
        pinned[key] = flag

    return LiveSettings(
        Settings.model_validate(data), path=path, file_data=file_data, pinned=pinned
    )


def _checked(data: dict, source: str) -> dict:
    try:
        Settings.model_validate(data)
    except ValidationError as error:
        raise SettingsError(f"{source}: {_describe(error)}") from error
    return data


class LiveSettings:
    """The settings in effect, changed through the API, saved on request.

    The current `Tuning` is an immutable snapshot, replaced whole under a
    lock. Readers -- every session, once per frame -- take the reference
    without locking: one assignment, so a frame sees either the old
    values or the new ones, never a mix of the two.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        path: Path | None = None,
        file_data: dict | None = None,
        pinned: Mapping[str, str] | None = None,
    ) -> None:
        self.startup = settings or Settings()
        self.path = path
        self.pinned = dict(pinned or {})
        self._file_data = dict(file_data or {})
        self._tuning = self.startup.tuning
        self._lock = threading.Lock()

    @property
    def tuning(self) -> Tuning:
        return self._tuning

    def update_tuning(
        self,
        changes: Mapping[str, float],
        apply: Callable[[Tuning], None] | None = None,
    ) -> Tuning:
        """Apply a partial change, validated whole, and return the result.

        `apply` pushes the result somewhere that does not read the
        snapshot itself (the cursor backend's relative scale). It runs
        under the same lock, so two concurrent changes reach it in the
        order they were made, and the last one pushed is the one in
        effect.
        """
        with self._lock:
            try:
                updated = Tuning.model_validate(
                    {**self._tuning.model_dump(), **changes}
                )
            except ValidationError as error:
                raise SettingsError(_describe(error)) from error
            self._tuning = updated
            if apply is not None:
                apply(updated)
            return updated

    def save(self, view: ViewPreferences) -> Path:
        """Write the tuning in effect and `view` to the file, atomically.

        A value pinned by a flag or environment variable and unchanged
        since startup keeps whatever the file said: saving must not turn
        a one-off override into the file's value.
        """
        if self.path is None:
            raise SettingsError("no settings file is configured")
        with self._lock:
            current = {"tuning": self._tuning.model_dump(), "view": view.model_dump()}
            startup = self.startup.model_dump()
            tables: dict[str, dict] = {}
            for table, values in current.items():
                on_file = self._file_data.get(table, {})
                written = {}
                for name, value in values.items():
                    key = f"{table}.{name}"
                    if key in self.pinned and value == startup[table][name]:
                        if name in on_file:
                            written[name] = on_file[name]
                        continue
                    written[name] = value
                tables[table] = written
            merged = {**self._file_data, **tables}
            atomic_write_text(self.path, _HEADER + dumps_toml(merged))
            self._file_data = merged
            return self.path


_HEADER = (
    "# Boresight settings. Written by the server when settings are saved\n"
    "# from the phone; comments are not preserved. Command-line flags and\n"
    "# BORESIGHT_* environment variables take precedence over this file.\n\n"
)


# --- Generic file helpers ----------------------------------------------


def atomic_write_text(path: Path, text: str) -> None:
    """Replace `path` with `text` so a reader never sees half of it.

    Written to a temporary file in the same directory (so the rename
    cannot cross filesystems), flushed to disk, then renamed over the
    target. A failure at any point leaves the previous file as it was.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def dumps_toml(data: Mapping) -> str:
    """Serialize what `tomllib` reads back as `data`.

    Covers what a settings file holds: tables, and strings, booleans,
    numbers, dates and arrays of those. Anything else raises rather than
    being written as something that would read back differently.
    """
    lines: list[str] = []
    _dump_table(data, (), lines)
    return "\n".join(lines).lstrip("\n") + "\n"


def _dump_table(table: Mapping, prefix: tuple[str, ...], lines: list[str]) -> None:
    scalars = {k: v for k, v in table.items() if not isinstance(v, Mapping)}
    tables = {k: v for k, v in table.items() if isinstance(v, Mapping)}
    if prefix and (scalars or not tables):
        lines.append("")
        lines.append(f"[{'.'.join(_key(part) for part in prefix)}]")
    for key, value in scalars.items():
        lines.append(f"{_key(key)} = {_value(value)}")
    for key, value in tables.items():
        _dump_table(value, (*prefix, key), lines)


def _key(key: str) -> str:
    return key if _BARE_KEY.match(key) else json.dumps(key)


def _value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # repr round-trips exactly and spells inf/nan the way TOML does.
        return repr(value)
    if isinstance(value, str):
        # A JSON string is a valid TOML basic string.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    if isinstance(value, Mapping):
        inner = ", ".join(f"{_key(k)} = {_value(v)}" for k, v in value.items())
        return "{" + inner + "}"
    raise TypeError(f"cannot write {type(value).__name__} to a settings file")
