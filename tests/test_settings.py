"""The settings model, its precedence, and writing it back to the file."""

from __future__ import annotations

import datetime
import os
import threading
import tomllib
from pathlib import Path

import pytest

from boresight.settings import (
    LiveSettings,
    Settings,
    SettingsError,
    Tuning,
    ViewPreferences,
    atomic_write_text,
    dumps_toml,
    resolve_settings,
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


# --- Precedence ------------------------------------------------------------


def test_a_missing_file_means_defaults(tmp_path: Path) -> None:
    live = resolve_settings(tmp_path / "absent.toml", env={})

    assert live.startup == Settings()
    assert live.pinned == {}


def test_the_file_overrides_defaults(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "config.toml",
        '[tuning]\nbeta = 2\n[view]\ndebug = true\nmarker_source = "screen"\n',
    )

    live = resolve_settings(path, env={})

    assert live.tuning.beta == 2.0
    assert live.tuning.min_cutoff == Tuning().min_cutoff
    assert live.startup.view == ViewPreferences(debug=True, marker_source="screen")


def test_an_env_var_beats_the_file(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", "[tuning]\nbeta = 2.0\n")

    live = resolve_settings(path, env={"BORESIGHT_AIM_BETA": "3.0"})

    assert live.tuning.beta == 3.0
    assert live.pinned == {"tuning.beta": "BORESIGHT_AIM_BETA"}


def test_a_flag_beats_an_env_var_and_the_file(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", "[tuning]\nbeta = 2.0\n")

    live = resolve_settings(
        path, env={"BORESIGHT_AIM_BETA": "3.0"}, cli={"tuning.beta": 4.0}
    )

    assert live.tuning.beta == 4.0
    assert live.pinned == {"tuning.beta": "--aim-beta"}


def test_an_unset_flag_does_not_pin(tmp_path: Path) -> None:
    live = resolve_settings(
        tmp_path / "c.toml", env={}, cli={"view.overlay_extra_margin_px": None}
    )

    assert live.pinned == {}


def test_an_empty_env_var_counts_as_unset(tmp_path: Path) -> None:
    live = resolve_settings(tmp_path / "c.toml", env={"BORESIGHT_REL_SCALE": ""})

    assert live.tuning.rel_scale == 0.0
    assert live.pinned == {}


def test_every_tuning_value_has_an_env_var(tmp_path: Path) -> None:
    live = resolve_settings(
        tmp_path / "c.toml",
        env={
            "BORESIGHT_AIM_MIN_CUTOFF": "2.5",
            "BORESIGHT_AIM_BETA": "0.3",
            "BORESIGHT_AIM_HOLD_S": "0.2",
            "BORESIGHT_REL_SCALE": "1000",
        },
    )

    assert live.tuning == Tuning(min_cutoff=2.5, beta=0.3, hold_s=0.2, rel_scale=1000)


# --- Refusing bad values ----------------------------------------------------


@pytest.mark.parametrize(
    ("env", "named"),
    [
        ({"BORESIGHT_REL_SCALE": "abc"}, "BORESIGHT_REL_SCALE"),
        ({"BORESIGHT_AIM_MIN_CUTOFF": "-1"}, "BORESIGHT_AIM_MIN_CUTOFF"),
        ({"BORESIGHT_AIM_BETA": "nan"}, "BORESIGHT_AIM_BETA"),
    ],
)
def test_a_bad_env_var_is_refused_by_name(tmp_path: Path, env, named) -> None:
    with pytest.raises(SettingsError, match=named):
        resolve_settings(tmp_path / "c.toml", env=env)


def test_a_bad_flag_is_refused_by_name(tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match="--aim-hold-s"):
        resolve_settings(tmp_path / "c.toml", env={}, cli={"tuning.hold_s": 60.0})


@pytest.mark.parametrize(
    ("text", "named"),
    [
        ("[tuning]\nmin_cutoff = -1\n", "min_cutoff"),
        ('[tuning]\nbeta = "2"\n', "beta"),
        ("[tuning]\nbeat = 2.0\n", "beat"),
        ('[view]\nmarker_source = "laser"\n', "marker_source"),
        ("[view]\noverlay_extra_margin_px = 1.5\n", "overlay_extra_margin_px"),
        ("tuning = 3\n", "tuning"),
        ("[tuning\n", "config.toml"),
    ],
)
def test_a_bad_file_is_refused_naming_it_and_the_value(
    tmp_path: Path, text: str, named: str
) -> None:
    path = _write(tmp_path / "config.toml", text)

    with pytest.raises(SettingsError) as error:
        resolve_settings(path, env={})

    assert str(path) in str(error.value)
    assert named in str(error.value)


def test_unknown_tables_are_ignored(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", "[calibration]\nx = 1\n")

    assert resolve_settings(path, env={}).startup == Settings()


# --- Live updates -----------------------------------------------------------


def test_a_partial_update_leaves_the_rest_alone() -> None:
    live = LiveSettings()

    updated = live.update_tuning({"hold_s": 0.3})

    assert updated == Tuning(hold_s=0.3)
    assert live.tuning is updated


def test_an_out_of_range_update_changes_nothing() -> None:
    live = LiveSettings()
    before = live.tuning

    with pytest.raises(SettingsError, match="beta"):
        live.update_tuning({"min_cutoff": 2.0, "beta": 50.0})

    assert live.tuning is before


def test_concurrent_updates_are_each_applied_whole() -> None:
    """Every snapshot a reader can see is one some update produced: the
    pairs always move together, never half of one and half of another."""
    live = LiveSettings()
    pairs = [(0.1 * i + 0.1, 0.1 * i) for i in range(1, 40)]
    seen: list[Tuning] = []
    done = threading.Event()

    def reader() -> None:
        while not done.is_set():
            seen.append(live.tuning)

    def writer(pair) -> None:
        live.update_tuning({"min_cutoff": pair[0], "beta": pair[1]})

    watcher = threading.Thread(target=reader)
    watcher.start()
    writers = [threading.Thread(target=writer, args=(pair,)) for pair in pairs]
    for thread in writers:
        thread.start()
    for thread in writers:
        thread.join()
    done.set()
    watcher.join()

    allowed = {pair for pair in pairs} | {(Tuning().min_cutoff, Tuning().beta)}
    assert {(t.min_cutoff, t.beta) for t in seen} <= allowed
    assert (live.tuning.min_cutoff, live.tuning.beta) in allowed


# --- Saving -----------------------------------------------------------------


def test_saving_writes_what_is_in_effect_and_reads_back(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "config.toml"
    live = resolve_settings(path, env={})
    live.update_tuning({"beta": 2.5})

    live.save(ViewPreferences(debug=True, overlay_extra_margin_px=40))

    again = resolve_settings(path, env={})
    assert again.tuning == Tuning(beta=2.5)
    assert again.startup.view == ViewPreferences(debug=True, overlay_extra_margin_px=40)


def test_an_untouched_override_is_not_saved(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", "[tuning]\nmin_cutoff = 0.8\n")
    live = resolve_settings(
        path,
        env={"BORESIGHT_AIM_BETA": "3.0", "BORESIGHT_AIM_MIN_CUTOFF": "4.0"},
    )

    live.save(ViewPreferences())

    saved = tomllib.loads(path.read_text())["tuning"]
    assert "beta" not in saved
    # Pinned and untouched: the file keeps its own value.
    assert saved["min_cutoff"] == 0.8


def test_a_changed_override_is_saved(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    live = resolve_settings(path, env={"BORESIGHT_AIM_BETA": "3.0"})
    live.update_tuning({"beta": 1.5})

    live.save(ViewPreferences())

    assert tomllib.loads(path.read_text())["tuning"]["beta"] == 1.5


def test_unknown_tables_survive_a_save(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "config.toml",
        '[calibration.phone]\noffset = [0.01, -0.02]\nname = "pixel"\n'
        "when = 2026-09-26T10:00:00\n",
    )
    live = resolve_settings(path, env={})

    live.save(ViewPreferences())

    data = tomllib.loads(path.read_text())
    assert data["calibration"] == {
        "phone": {
            "offset": [0.01, -0.02],
            "name": "pixel",
            "when": datetime.datetime(2026, 9, 26, 10, 0),
        }
    }


def test_saving_without_a_path_is_refused() -> None:
    with pytest.raises(SettingsError):
        LiveSettings().save(ViewPreferences())


def test_a_failed_write_keeps_the_old_file(tmp_path: Path, monkeypatch) -> None:
    path = _write(tmp_path / "config.toml", "[tuning]\nbeta = 2.0\n")
    live = resolve_settings(path, env={})

    def fail(*_args) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        live.save(ViewPreferences(debug=True))

    assert path.read_text() == "[tuning]\nbeta = 2.0\n"
    assert [p.name for p in tmp_path.iterdir()] == ["config.toml"]


def test_atomic_write_creates_the_directory(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b.toml"

    atomic_write_text(path, "x = 1\n")

    assert path.read_text() == "x = 1\n"


def test_dumps_toml_round_trips() -> None:
    data = {
        "top": 1,
        "t": {
            "f": 0.1,
            "big": 1e20,
            "s": 'quote " and\nnewline',
            "b": False,
            "list": [1, 2],
            "sub": {"k": "v"},
        },
        "empty": {},
        "with space": {"odd key": 1},
    }

    assert tomllib.loads(dumps_toml(data)) == data


def test_dumps_toml_refuses_what_it_cannot_write() -> None:
    with pytest.raises(TypeError):
        dumps_toml({"t": {"x": object()}})
