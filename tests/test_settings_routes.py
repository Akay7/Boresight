"""Runtime settings over HTTP: reading, live changes, saving, restoring."""

from __future__ import annotations

import functools
import json
import logging
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boresight import marker_source, server
from boresight.inject import FakeCursorBackend
from boresight.marker_source import MarkerSourceController
from boresight.netaccess import ServerConfig
from boresight.one_euro import OneEuroFilter
from boresight.server import FRAME_SOCKET_PATH, create_app
from boresight.settings import TUNING_RANGES, Tuning, resolve_settings
from boresight.stream import pack_frame

VIDEO_DIR = Path(__file__).parent / "fixtures" / "synthetic_video"
TOKEN = "a-shared-token"

REPORTS = (
    "import json,time;"
    'print(json.dumps({"event":"overlay-ready","screen_px":[1920,1080],'
    '"tag_px":86,"inset_px":22}), flush=True);'
    "time.sleep(60)"
)
REFUSES = (
    'import sys;sys.stderr.write("this compositor cannot host an overlay");sys.exit(2)'
)


class _ScaledBackend(FakeCursorBackend):
    """A fake that, like the uinput backend, has a relative scale."""

    rel_scale = 0.0


def _frame_payload() -> bytes:
    manifest = json.loads((VIDEO_DIR / "manifest.json").read_text())
    return (VIDEO_DIR / manifest["frames"][0]["file"]).read_bytes()


def _client(tmp_path: Path, text: str | None = None, env=None, **kwargs):
    path = tmp_path / "config.toml"
    if text is not None:
        path.write_text(text)
    live = resolve_settings(path, env=env or {})
    backend = kwargs.pop("backend", None) or FakeCursorBackend()
    app = create_app(backend_factory=lambda: backend, settings=live, **kwargs)
    return TestClient(app)


# --- Reading ----------------------------------------------------------------


def test_settings_can_be_read_with_ranges_and_pins(tmp_path: Path) -> None:
    with _client(tmp_path, env={"BORESIGHT_AIM_BETA": "3.0"}) as client:
        state = client.get("/settings").json()

    assert state["tuning"] == Tuning(beta=3.0).model_dump()
    assert state["view"] == {
        "debug": False,
        "marker_source": "printed",
        "overlay_extra_margin_px": 0,
    }
    assert set(state["limits"]) == set(TUNING_RANGES)
    assert state["limits"]["beta"]["max"] == TUNING_RANGES["beta"][1]
    assert state["pinned"] == {"tuning.beta": "BORESIGHT_AIM_BETA"}
    assert state["path"] == str(tmp_path / "config.toml")
    assert state["rel_scale_supported"] is False


def test_settings_are_not_readable_without_the_token(tmp_path: Path) -> None:
    with _client(tmp_path, config=ServerConfig(token=TOKEN)) as client:
        refused = client.get("/settings")
        refused_update = client.post("/settings/tuning", json={"beta": 2.0})
        refused_save = client.post("/settings/save")
        allowed = client.get("/settings", headers={"Authorization": f"Bearer {TOKEN}"})

    assert refused.status_code == 401
    assert refused_update.status_code == 401
    assert refused_save.status_code == 401
    assert allowed.status_code == 200
    assert not (tmp_path / "config.toml").exists()


# --- Changing ---------------------------------------------------------------


def test_a_partial_update_changes_only_what_it_names(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/settings/tuning", json={"hold_s": 0.3})

    assert response.status_code == 200
    assert response.json()["tuning"] == Tuning(hold_s=0.3).model_dump()


@pytest.mark.parametrize(
    "body",
    [
        {"beta": 50},
        {"min_cutoff": 0},
        {"hold_s": -1},
        {"rel_scale": "lots"},
        {"beat": 1.0},
    ],
)
def test_an_invalid_update_is_refused_and_changes_nothing(
    tmp_path: Path, body: dict
) -> None:
    with _client(tmp_path) as client:
        response = client.post("/settings/tuning", json={"min_cutoff": 2.0, **body})
        after = client.get("/settings").json()

    assert response.status_code == 422
    assert after["tuning"] == Tuning().model_dump()


def test_the_relative_scale_reaches_the_backend(tmp_path: Path) -> None:
    backend = _ScaledBackend()
    with _client(tmp_path, "[tuning]\nrel_scale = 500.0\n", backend=backend) as client:
        assert backend.rel_scale == 500.0
        assert client.get("/settings").json()["rel_scale_supported"] is True

        client.post("/settings/tuning", json={"rel_scale": 1200})

    assert backend.rel_scale == 1200.0


def test_a_streaming_session_follows_a_change_on_its_next_frame(
    tmp_path: Path, monkeypatch
) -> None:
    filters: list[OneEuroFilter] = []

    def recording(tuning: Tuning) -> OneEuroFilter:
        filters.append(OneEuroFilter(tuning.min_cutoff, tuning.beta))
        return filters[-1]

    monkeypatch.setattr(marker_source, "_aim_filter", recording)
    payload = _frame_payload()

    with _client(tmp_path) as client:
        with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
            socket.send_bytes(pack_frame(1000.0, payload))
            assert socket.receive_json()["outcome"] == "solved"

            client.post("/settings/tuning", json={"min_cutoff": 3.0, "beta": 0.2})
            socket.send_bytes(pack_frame(1050.0, payload))
            assert socket.receive_json()["outcome"] == "solved"

    # One session, one filter: tuned in place, never rebuilt.
    assert len(filters) == 1
    assert (filters[0].min_cutoff, filters[0].beta) == (3.0, 0.2)


# --- Saving -----------------------------------------------------------------


def test_saved_settings_come_back_after_a_restart(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        client.post("/settings/tuning", json={"beta": 2.5})
        client.post("/debug", json={"enabled": True})
        client.post("/markers/overlay-margin", json={"extra_margin_px": 40})
        response = client.post("/settings/save")

    assert response.status_code == 200
    saved = tomllib.loads((tmp_path / "config.toml").read_text())
    assert saved["tuning"]["beta"] == 2.5

    with _client(tmp_path) as client:
        state = client.get("/settings").json()
        debug = client.get("/debug").json()
        margin = client.get("/markers/source").json()["overlay_extra_margin_px"]

    assert state["tuning"]["beta"] == 2.5
    assert debug == {"enabled": True}
    assert margin == 40


def test_saving_without_a_file_is_a_conflict(tmp_path: Path) -> None:
    app = create_app(backend_factory=FakeCursorBackend)
    with TestClient(app) as client:
        response = client.post("/settings/save")

    assert response.status_code == 409
    assert response.json()["path"] is None


def test_a_failed_save_is_reported(tmp_path: Path) -> None:
    # A directory where the file should be: the rename cannot replace it.
    (tmp_path / "config.toml").mkdir()
    with _client(tmp_path) as client:
        response = client.post("/settings/save")

    assert response.status_code == 500
    assert "could not save" in response.json()["detail"]


# --- Restoring the marker source --------------------------------------------


def _launching(monkeypatch, body: str) -> None:
    def launch(command, **kwargs):
        return subprocess.Popen([sys.executable, "-c", body], **kwargs)

    monkeypatch.setattr(
        server,
        "MarkerSourceController",
        functools.partial(MarkerSourceController, launcher=launch),
    )


def _wait_for(client: TestClient, done) -> dict:
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        state = client.get("/markers/source").json()
        if done(state):
            return state
        time.sleep(0.05)
    raise AssertionError(f"marker source never settled: {state}")


def test_saved_on_screen_markers_are_restored(tmp_path: Path, monkeypatch) -> None:
    _launching(monkeypatch, REPORTS)

    with _client(tmp_path, '[view]\nmarker_source = "screen"\n') as client:
        state = _wait_for(client, lambda s: s["source"] == "screen")

    assert state["overlay_running"] is True


def test_a_failed_restore_leaves_printed_markers(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    caplog.set_level(logging.WARNING, logger="boresight")
    _launching(monkeypatch, REFUSES)

    with _client(tmp_path, '[view]\nmarker_source = "screen"\n') as client:
        state = _wait_for(client, lambda s: s["error"] is not None)

    assert state["source"] == "printed"
    assert any("could not restore" in r.getMessage() for r in caplog.records)


# --- Startup ----------------------------------------------------------------


def test_main_refuses_a_bad_env_var(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("BORESIGHT_REL_SCALE", "abc")

    with pytest.raises(SystemExit) as exit_:
        server.main(["--config", str(tmp_path / "c.toml")])

    assert exit_.value.code == 2
    assert "BORESIGHT_REL_SCALE" in capsys.readouterr().err


def test_main_passes_resolved_settings_to_the_app(tmp_path: Path, monkeypatch) -> None:
    import uvicorn

    path = tmp_path / "c.toml"
    path.write_text("[tuning]\nbeta = 2.0\nhold_s = 0.5\n")
    monkeypatch.setenv("BORESIGHT_AIM_HOLD_S", "0.4")
    for variable in ("BORESIGHT_AIM_BETA", "BORESIGHT_AIM_MIN_CUTOFF"):
        monkeypatch.delenv(variable, raising=False)
    built: dict = {}
    monkeypatch.setattr(server, "create_app", lambda **kwargs: built.update(kwargs))
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)

    server.main(["--config", str(path), "--aim-min-cutoff", "1.5"])

    settings = built["settings"]
    assert settings.tuning == Tuning(min_cutoff=1.5, beta=2.0, hold_s=0.4)
    assert settings.pinned == {
        "tuning.min_cutoff": "--aim-min-cutoff",
        "tuning.hold_s": "BORESIGHT_AIM_HOLD_S",
    }


# --- The phone page ---------------------------------------------------------


def test_the_page_carries_the_tuning_panel(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        page = client.get("/").text
        script = client.get("/capture.js").text

    assert 'id="tuning"' in page
    assert 'id="tuning-save"' in page
    # Every tuning value the server has gets a slider, by the same key.
    for key in TUNING_RANGES:
        assert f'key: "{key}"' in script
    for path in ('"settings"', '"settings/tuning"', '"settings/save"'):
        assert f"sameOriginUrl({path})" in script
