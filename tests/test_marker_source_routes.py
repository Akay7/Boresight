"""The marker source over HTTP, and switching while a phone streams.

The mid-stream test is the one worth reading: it is the difference
between a switch that reaches a connected phone and one that silently
does not, which was a real risk before the session stopped capturing
the pipeline at connect time.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boresight.inject import FakeCursorBackend
from boresight.marker_source import MarkerSource, MarkerSourceController
from boresight.netaccess import ServerConfig
from boresight.server import FRAME_SOCKET_PATH, create_app
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


def _launcher(body: str):
    started: list[list[str]] = []

    def launch(command, **kwargs):
        started.append(command)
        return subprocess.Popen([sys.executable, "-c", body], **kwargs)

    launch.started = started
    return launch


@pytest.fixture
def backend() -> FakeCursorBackend:
    return FakeCursorBackend()


def _client(backend, body: str = REPORTS, token: str | None = None):
    app = create_app(backend_factory=lambda: backend, config=ServerConfig(token=token))
    launch = _launcher(body)
    client = TestClient(app)

    # Replace the controller's launcher once the app has built one.
    def patched():
        controller = client.app.state.markers
        controller._launcher = launch  # noqa: SLF001

    client._patch_launcher = patched  # type: ignore[attr-defined]
    client._launch = launch  # type: ignore[attr-defined]
    return client


# --- Reading and setting ----------------------------------------------


def test_the_current_source_can_be_read(backend) -> None:
    with _client(backend) as client:
        state = client.get("/markers/source").json()

    assert state["source"] == "printed"
    assert state["overlay_running"] is False


def test_selecting_on_screen_markers_reports_the_new_state(backend) -> None:
    with _client(backend) as client:
        client._patch_launcher()
        response = client.post("/markers/source", json={"source": "screen"})
        state = response.json()

        assert response.status_code == 200
        assert state["source"] == "screen"
        assert state["geometry"]["screen_px"] == [1920, 1080]
        assert client.get("/markers/source").json()["source"] == "screen"


def test_selecting_printed_markers_stops_the_overlay(backend) -> None:
    with _client(backend) as client:
        client._patch_launcher()
        client.post("/markers/source", json={"source": "screen"})
        state = client.post("/markers/source", json={"source": "printed"}).json()

    assert state["source"] == "printed"
    assert state["overlay_running"] is False


def test_an_unknown_source_is_rejected(backend) -> None:
    with _client(backend) as client:
        assert client.post("/markers/source", json={"source": "laser"}).status_code == (
            422
        )


def test_a_failed_selection_is_reported_as_a_failure(backend) -> None:
    """Not a 200 with the old state. The phone has to be able to tell
    'it worked' from 'it did not', or it will show the wrong thing."""
    with _client(backend, body=REFUSES) as client:
        client._patch_launcher()
        response = client.post("/markers/source", json={"source": "screen"})

    assert response.status_code == 409
    body = response.json()
    assert "cannot host an overlay" in body["detail"]
    assert body["source"] == "printed"


# --- Switching mid-stream ---------------------------------------------


def test_switching_mid_stream_changes_the_layout_for_the_next_frame(
    backend,
) -> None:
    """Before the session read the pipeline per frame, a switch would
    never have reached an already-connected phone: it would have gone on
    solving against the layout current when it connected."""
    manifest = json.loads((VIDEO_DIR / "manifest.json").read_text())
    entry = manifest["frames"][0]
    frame = (VIDEO_DIR / entry["file"]).read_bytes()

    with _client(backend) as client:
        client._patch_launcher()
        with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
            socket.send_bytes(pack_frame(0.0, frame))
            before = socket.receive_json()

            # Switch while the socket stays open.
            assert (
                client.post("/markers/source", json={"source": "screen"}).status_code
                == 200
            )

            socket.send_bytes(pack_frame(0.0, frame))
            after = socket.receive_json()

    # Same frame, different layout: the printed layout solves it, the
    # on-screen layout does not describe these tags at all.
    assert before["outcome"] == "solved"
    assert before["markers_detected"] == 8
    assert after["x"] != before["x"] or after["outcome"] != before["outcome"]


def test_the_connection_survives_a_switch(backend) -> None:
    manifest = json.loads((VIDEO_DIR / "manifest.json").read_text())
    frame = (VIDEO_DIR / manifest["frames"][0]["file"]).read_bytes()

    with _client(backend) as client:
        client._patch_launcher()
        with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
            socket.send_bytes(pack_frame(0.0, frame))
            socket.receive_json()
            client.post("/markers/source", json={"source": "screen"})
            client.post("/markers/source", json={"source": "printed"})
            socket.send_bytes(pack_frame(0.0, frame))
            final = socket.receive_json()

    # Still the same session: counts continued rather than restarting.
    assert final["received"] == 2
    assert final["outcome"] == "solved"


# --- Shutdown ----------------------------------------------------------


def test_the_overlay_is_terminated_when_the_server_stops(backend) -> None:
    """The failure this most prevents: an overlay that takes no input
    and has no title bar, left on screen with its parent gone."""
    client = _client(backend)
    with client:
        client._patch_launcher()
        client.post("/markers/source", json={"source": "screen"})
        process = client.app.state.markers._process  # noqa: SLF001
        assert process.poll() is None

    assert process.poll() is not None


# --- Authentication ----------------------------------------------------


def test_reading_the_source_requires_the_token(backend) -> None:
    with _client(backend, token=TOKEN) as client:
        assert client.get("/markers/source").status_code == 401


def test_selecting_a_source_requires_the_token_and_starts_nothing(backend) -> None:
    with _client(backend, token=TOKEN) as client:
        client._patch_launcher()
        response = client.post("/markers/source", json={"source": "screen"})

        assert response.status_code == 401
        assert client._launch.started == []


def test_an_authorised_client_can_select(backend) -> None:
    with _client(backend, token=TOKEN) as client:
        client._patch_launcher()
        response = client.post(
            f"/markers/source?token={TOKEN}", json={"source": "screen"}
        )

    assert response.status_code == 200


# --- The command line ---------------------------------------------------


def test_request_content_never_reaches_the_child_command(backend) -> None:
    with _client(backend) as client:
        client._patch_launcher()
        client.post("/markers/source", json={"source": "screen"})

        assert client._launch.started == [[sys.executable, "-m", "boresight.overlay"]]


def test_the_display_index_comes_from_startup_not_the_request(backend) -> None:
    app = create_app(backend_factory=lambda: backend, display=1)
    launch = _launcher(REPORTS)

    with TestClient(app) as client:
        client.app.state.markers._launcher = launch  # noqa: SLF001
        client.post("/markers/source", json={"source": "screen"})

    assert launch.started[0][-2:] == ["--display", "1"]


def test_the_default_launcher_is_the_real_one() -> None:
    """Built without an override, the controller would start a real
    overlay -- so nothing in this file may construct one and select
    on-screen markers without substituting a launcher first."""
    from boresight.layout_source import resolve_layout

    controller = MarkerSourceController(FakeCursorBackend(), resolve_layout("file"))

    assert controller.source is MarkerSource.PRINTED
    assert controller._launcher is subprocess.Popen  # noqa: SLF001


# --- The viewfinder overlay setting -----------------------------------


def test_the_overlay_setting_is_remembered_by_the_server(backend) -> None:
    """So the phone renders the right button on load, and a reload does
    not silently drop a setting the operator chose."""
    with _client(backend) as client:
        assert client.get("/debug").json() == {"enabled": False}

        assert client.post("/debug", json={"enabled": True}).json() == {"enabled": True}
        assert client.get("/debug").json() == {"enabled": True}


def test_a_new_session_inherits_the_remembered_setting(backend) -> None:
    manifest = json.loads((VIDEO_DIR / "manifest.json").read_text())
    frame = (VIDEO_DIR / manifest["frames"][0]["file"]).read_bytes()

    with _client(backend) as client:
        client.post("/debug", json={"enabled": True})

        with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
            socket.send_bytes(pack_frame(0.0, frame))
            report = socket.receive_json()

    # No control message was sent on this socket at all.
    assert "debug" in report


def test_a_session_started_before_the_change_keeps_its_own_flag(backend) -> None:
    """The isolation the debug feature was built with: one AimPipeline
    serves every connection, so a live session's flag has to be its own
    or one phone's overlay would change another phone's frames."""
    manifest = json.loads((VIDEO_DIR / "manifest.json").read_text())
    frame = (VIDEO_DIR / manifest["frames"][0]["file"]).read_bytes()

    with _client(backend) as client:
        with client.websocket_connect(FRAME_SOCKET_PATH) as already_open:
            client.post("/debug", json={"enabled": True})

            already_open.send_bytes(pack_frame(0.0, frame))
            report = already_open.receive_json()

    assert "debug" not in report


def test_toggling_over_the_socket_is_remembered_too(backend) -> None:
    """However the operator flipped it, the button comes back that way."""
    manifest = json.loads((VIDEO_DIR / "manifest.json").read_text())
    frame = (VIDEO_DIR / manifest["frames"][0]["file"]).read_bytes()

    with _client(backend) as client:
        with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
            socket.send_text(json.dumps({"type": "debug", "enabled": True}))
            socket.send_bytes(pack_frame(0.0, frame))
            socket.receive_json()

        assert client.get("/debug").json() == {"enabled": True}


def test_the_overlay_setting_requires_the_token(backend) -> None:
    with _client(backend, token=TOKEN) as client:
        assert client.get("/debug").status_code == 401
        assert client.post("/debug", json={"enabled": True}).status_code == 401


def test_a_non_boolean_setting_is_rejected(backend) -> None:
    with _client(backend) as client:
        assert client.post("/debug", json={"enabled": "yes please"}).status_code == 422
        assert client.get("/debug").json() == {"enabled": False}
