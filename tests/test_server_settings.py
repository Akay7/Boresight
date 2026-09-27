"""Every server option lives in the settings file; flags override it.

Resolution is tested on `resolve_settings` directly, and the wiring by
running `server.main` with uvicorn and the app stubbed out, capturing
what the server would have been started with.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from boresight import server
from boresight.detect import TrackerOptions
from boresight.settings import SettingsError, ViewPreferences, resolve_settings


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_every_table_defaults_without_a_file(tmp_path: Path) -> None:
    startup = resolve_settings(tmp_path / "none.toml", env={}).startup
    assert startup.server.port == 7331
    assert startup.server.qr is True
    assert startup.markers.layout == "file"
    assert startup.detection.tracker() == TrackerOptions()
    assert startup.recording.seconds == 10.0


def test_the_new_tables_come_from_the_file(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "config.toml",
        "[server]\nport = 9100\ntls = true\nqr = false\n"
        '[markers]\nlayout = "screen:1920x1080"\n'
        "[detection]\ncoarse_min_side_px = 48\nfull_pass_every = 5\n"
        "[recording]\nseconds = 5\nmax_mb = 16\n",
    )
    startup = resolve_settings(path, env={}).startup
    assert startup.server.port == 9100
    assert startup.server.tls is True
    assert startup.server.qr is False
    assert startup.markers.layout == "screen:1920x1080"
    assert startup.detection.tracker() == TrackerOptions(
        min_side_px=48.0, full_pass_every=5
    )
    assert (startup.recording.seconds, startup.recording.max_mb) == (5.0, 16.0)


def test_tracking_off_means_no_tracker(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", "[detection]\ntracked = false\n")
    assert resolve_settings(path, env={}).startup.detection.tracker() is None


def test_a_flag_overrides_a_file_boolean_either_way(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", "[server]\ntls = true\nqr = false\n")
    live = resolve_settings(path, env={}, cli={"server.tls": False, "server.qr": True})
    assert live.startup.server.tls is False
    assert live.startup.server.qr is True


@pytest.mark.parametrize(
    ("text", "named"),
    [
        ("[server]\nport = 0\n", "port"),
        ('[server]\nport = "9100"\n', "port"),
        ('[server]\ntoken = ""\n', "token"),
        ("[detection]\nfull_pass_every = 0\n", "full_pass_every"),
        ("[recording]\nseconds = -1\n", "seconds"),
        ("[server]\nprot = 9100\n", "prot"),
    ],
)
def test_a_bad_value_in_a_new_table_is_refused(
    tmp_path: Path, text: str, named: str
) -> None:
    path = _write(tmp_path / "config.toml", text)
    with pytest.raises(SettingsError, match=named) as raised:
        resolve_settings(path, env={})
    assert str(path) in str(raised.value)


def test_a_bad_flag_is_refused_by_its_name(tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match="--port"):
        resolve_settings(tmp_path / "none.toml", env={}, cli={"server.port": 70000})


def test_saving_keeps_the_files_own_server_table(tmp_path: Path) -> None:
    """A flag overriding `[server]` for one run is never written back."""
    path = _write(tmp_path / "config.toml", "[server]\nport = 9100\ntls = true\n")
    live = resolve_settings(path, env={}, cli={"server.port": 9200})
    live.save(ViewPreferences(debug=True))

    data = tomllib.loads(path.read_text())
    assert data["server"] == {"port": 9100, "tls": True}
    assert data["view"]["debug"] is True


# --- Wiring in server.main ------------------------------------------------


@pytest.fixture
def started(monkeypatch, tmp_path: Path):
    """Run `server.main` with a settings file, capturing the start-up."""
    captured: dict = {}
    monkeypatch.setattr(
        "uvicorn.run", lambda app, **kwargs: captured.setdefault("run", kwargs)
    )
    monkeypatch.setattr(
        server, "create_app", lambda **kwargs: captured.setdefault("app", kwargs)
    )
    config = tmp_path / "config.toml"

    def start(text: str, *flags: str) -> dict:
        _write(config, text)
        server.main(["--config", str(config), *flags])
        return captured

    return start


def test_main_listens_where_the_file_says(started) -> None:
    captured = started('[server]\nhost = "127.0.0.1"\nport = 9100\n')
    assert captured["run"]["host"] == "127.0.0.1"
    assert captured["run"]["port"] == 9100


def test_a_flag_beats_the_file_in_main(started) -> None:
    captured = started("[server]\nport = 9100\n", "--port", "9200")
    assert captured["run"]["port"] == 9200


def test_main_takes_detection_and_recording_from_the_file(started) -> None:
    captured = started(
        "[detection]\ncoarse_min_side_px = 48\n[recording]\nseconds = 5\nmax_mb = 1\n"
    )
    app = captured["app"]
    assert app["tracked_detection"] == TrackerOptions(min_side_px=48.0)
    assert app["recording"].seconds == 5.0
    assert app["recording"].max_bytes == 1024 * 1024


def test_full_frame_detection_overrides_the_file(started) -> None:
    captured = started("[detection]\ntracked = true\n", "--full-frame-detection")
    assert captured["app"]["tracked_detection"] is None


def test_the_token_can_come_from_the_file(started) -> None:
    captured = started('[server]\nhost = "0.0.0.0"\ntoken = "file-token-7a1e"\n')
    assert captured["app"]["config"].token == "file-token-7a1e"


def test_an_exposed_server_without_a_token_still_refuses(started) -> None:
    with pytest.raises(SystemExit) as raised:
        started('[server]\nhost = "0.0.0.0"\n')
    assert raised.value.code == 2


def test_a_bad_layout_in_the_file_refuses_to_start(started) -> None:
    with pytest.raises(SystemExit) as raised:
        started('[markers]\nlayout = "nonsense"\n')
    assert raised.value.code == 2
