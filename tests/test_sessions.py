"""Which device a session is, and watching one that has no screen.

An ESP32-CAM inside a gun shell cannot show its own telemetry the way
the phone page does, so the server has to answer for it: `hello` names
the client, and `GET /sessions` lists what every live session last
reported. Both are additions a client that never uses them must not
notice.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boresight.inject import FakeCursorBackend
from boresight.netaccess import ServerConfig
from boresight.server import FRAME_SOCKET_PATH, create_app
from boresight.stream import SessionRegistry, SessionStats, pack_frame

VIDEO_DIR = Path(__file__).parent / "fixtures" / "synthetic_video"
CLIENT_MS = 1000.0
TOKEN = "correct-horse-battery-staple"


def _first_frame() -> bytes:
    manifest = json.loads((VIDEO_DIR / "manifest.json").read_text())
    return (VIDEO_DIR / manifest["frames"][0]["file"]).read_bytes()


@pytest.fixture
def backend() -> FakeCursorBackend:
    return FakeCursorBackend()


@pytest.fixture
def client(backend: FakeCursorBackend) -> TestClient:
    with TestClient(create_app(backend_factory=lambda: backend)) as test_client:
        yield test_client


def _hello(**fields) -> str:
    return json.dumps({"type": "hello", **fields})


def _send_frame(socket) -> dict:
    socket.send_bytes(pack_frame(CLIENT_MS, _first_frame()))
    return socket.receive_json()


def _sessions(client: TestClient) -> list[dict]:
    response = client.get("/sessions")
    assert response.status_code == 200
    return response.json()["sessions"]


# --- hello --------------------------------------------------------------


def test_an_identified_streaming_session_is_listed(client: TestClient) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(
            _hello(client="esp32-cam", version="0.1.0", frame_size=[800, 600])
        )
        socket.send_text(json.dumps({"type": "rtt", "ms": 42.5}))
        report = _send_frame(socket)
        sessions = _sessions(client)

    assert report["outcome"] == "solved"
    assert len(sessions) == 1
    entry = sessions[0]
    assert entry["client"] == "esp32-cam"
    assert entry["version"] == "0.1.0"
    assert entry["frame_size"] == [800, 600]
    assert entry["connected_s"] >= 0
    assert entry["stats"]["processed"] == 1
    assert entry["stats"]["round_trip_ms"] == 42.5
    assert entry["stats"]["outcome"] == "solved"


def test_a_session_that_never_says_hello_is_unaffected(client: TestClient) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        report = _send_frame(socket)
        sessions = _sessions(client)

    assert report["outcome"] == "solved"
    assert "client" not in report  # the wire payload itself is unchanged
    assert [entry["client"] for entry in sessions] == ["unidentified"]


@pytest.mark.parametrize(
    "hello",
    [
        _hello(),
        _hello(client=7),
        _hello(client="   "),
        _hello(client=None, version="0.1.0"),
    ],
)
def test_a_malformed_hello_is_ignored(client: TestClient, hello: str) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(hello)
        report = _send_frame(socket)
        sessions = _sessions(client)

    assert report["outcome"] == "solved"
    assert sessions[0]["client"] == "unidentified"
    assert sessions[0]["version"] is None


@pytest.mark.parametrize("frame_size", [[0, 600], ["800", 600], [True, 1], [800]])
def test_an_unreadable_frame_size_is_dropped_but_the_kind_kept(
    client: TestClient, frame_size: list
) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(_hello(client="esp32-cam", frame_size=frame_size))
        _send_frame(socket)
        sessions = _sessions(client)

    assert sessions[0]["client"] == "esp32-cam"
    assert sessions[0]["frame_size"] is None


def test_logs_name_the_client_kind(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="boresight")

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(_hello(client="esp32-cam", version="0.1.0"))
        _send_frame(socket)

    messages = [record.getMessage() for record in caplog.records]
    assert any(m.startswith("client identified: esp32-cam") for m in messages)
    assert any(m.startswith("first frame received from esp32-cam") for m in messages)
    assert any(m.startswith("client disconnected: esp32-cam") for m in messages)
    assert not any("phone" in m for m in messages)


# --- GET /sessions -------------------------------------------------------


def test_a_closed_session_leaves_the_listing(client: TestClient) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(_hello(client="esp32-cam"))
        _send_frame(socket)
        assert len(_sessions(client)) == 1

    assert _sessions(client) == []


def test_concurrent_sessions_are_listed_separately(client: TestClient) -> None:
    with (
        client.websocket_connect(FRAME_SOCKET_PATH) as camera,
        client.websocket_connect(FRAME_SOCKET_PATH) as phone,
    ):
        camera.send_text(_hello(client="esp32-cam"))
        phone.send_text(_hello(client="phone"))
        _send_frame(camera)
        _send_frame(phone)
        kinds = sorted(entry["client"] for entry in _sessions(client))

    assert kinds == ["esp32-cam", "phone"]


def test_debug_geometry_is_not_exposed_in_the_listing(client: TestClient) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(json.dumps({"type": "debug", "enabled": True}))
        report = _send_frame(socket)
        sessions = _sessions(client)

    assert report["debug"] is not None  # the client that asked still gets it
    assert "debug" not in sessions[0]["stats"]


def test_the_listing_requires_the_token(backend: FakeCursorBackend) -> None:
    app = create_app(backend_factory=lambda: backend, config=ServerConfig(token=TOKEN))
    with TestClient(app) as test_client:
        assert test_client.get("/sessions").status_code == 401
        assert test_client.get(f"/sessions?token={TOKEN}").status_code == 200


def test_the_registry_forgets_what_it_is_told_to() -> None:
    registry = SessionRegistry()
    first = registry.register("10.0.0.2:1", SessionStats(), started=0.0)
    second = registry.register("10.0.0.3:1", SessionStats(), started=0.0)

    registry.unregister(first)
    registry.unregister(first)  # a second removal is harmless

    assert len(registry) == 1
    assert [entry["address"] for entry in registry.listing(now=1.0)] == [second.address]
