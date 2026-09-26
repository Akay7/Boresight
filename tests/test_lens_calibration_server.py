"""Lens calibration through the server: applying a stored lens per
session, and calibrating a session from the phone or over HTTP.

A session that never calibrates must not notice any of it, so several
tests pin that its telemetry is exactly what it was.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from lens_render import distortion_maps, random_board_views

from boresight import server
from boresight.calibration import CalibrationCapture
from boresight.inject import FakeCursorBackend
from boresight.lens import LensModel, LensStore, lens_key
from boresight.netaccess import ServerConfig
from boresight.server import FRAME_SOCKET_PATH, create_app
from boresight.stream import pack_frame

VIDEO_DIR = Path(__file__).parent / "fixtures" / "synthetic_video"
VIDEO_SIZE = (1280, 720)


def _first_frame() -> bytes:
    manifest = json.loads((VIDEO_DIR / "manifest.json").read_text())
    return (VIDEO_DIR / manifest["frames"][0]["file"]).read_bytes()


@pytest.fixture
def store(tmp_path) -> LensStore:
    return LensStore(tmp_path / "lenses.json")


@pytest.fixture
def client(store: LensStore) -> TestClient:
    app = create_app(
        backend_factory=FakeCursorBackend, lens_store_factory=lambda: store
    )
    with TestClient(app) as test_client:
        yield test_client


def _send(socket, jpeg: bytes, client_ms: float = 1000.0) -> dict:
    socket.send_bytes(pack_frame(client_ms, jpeg))
    return socket.receive_json()


def _hello(**fields) -> str:
    return json.dumps({"type": "hello", **fields})


def _calibrate(action) -> str:
    return json.dumps({"type": "calibrate", "action": action})


def _video_lens() -> LensModel:
    # Near-identity at the fixture's size: the frame still solves.
    return LensModel(
        np.array([[1000.0, 0.0, 640.0], [0.0, 1000.0, 360.0], [0.0, 0.0, 1.0]]),
        np.array([-0.01, 0.0, 0.0, 0.0, 0.0]),
        VIDEO_SIZE,
        rms_px=0.25,
        views=20,
    )


# --- Applying a stored lens -------------------------------------------


def test_an_uncalibrated_session_reports_as_before(client: TestClient) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(_hello(client="phone", camera="back"))
        report = _send(socket, _first_frame())

    assert report["outcome"] == "solved"
    assert "lens" not in report
    assert "calibration" not in report


def test_a_matching_calibration_is_applied(client: TestClient, store) -> None:
    store.put(lens_key("phone", "back", VIDEO_SIZE), _video_lens())
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(_hello(client="phone", camera="back"))
        report = _send(socket, _first_frame())
        listing = client.get("/sessions").json()["sessions"]

    assert report["outcome"] == "solved"
    assert report["lens"] == {"rms_px": 0.25}
    assert listing[0]["camera"] == "back"


def test_another_camera_is_not_corrected(client: TestClient, store) -> None:
    store.put(lens_key("phone", "back", VIDEO_SIZE), _video_lens())
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(_hello(client="phone", camera="wide"))
        assert "lens" not in _send(socket, _first_frame())


def test_a_non_string_camera_is_ignored(client: TestClient) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(_hello(client="phone", camera=3))
        _send(socket, _first_frame())
        entry = client.get("/sessions").json()["sessions"][0]

    assert entry["client"] == "phone"
    assert entry["camera"] is None


# --- Calibrating over the socket ----------------------------------------


def test_calibration_progress_is_reported(client: TestClient) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(_calibrate("start"))
        started = _send(socket, _first_frame())
        socket.send_text(_calibrate("cancel"))
        cancelled = _send(socket, _first_frame(), 1050.0)

    # No board in the aim fixture: capturing, nothing kept, aim unharmed.
    assert started["outcome"] == "solved"
    assert started["calibration"]["state"] == "capturing"
    assert started["calibration"]["views"] == 0
    assert cancelled["calibration"]["state"] == "cancelled"


def test_an_unknown_calibrate_action_is_ignored(client: TestClient) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(_calibrate("explode"))
        assert "calibration" not in _send(socket, _first_frame())


def test_a_session_calibrates_end_to_end(
    client: TestClient, store, monkeypatch
) -> None:
    monkeypatch.setattr(
        server,
        "CalibrationCapture",
        functools.partial(CalibrationCapture, views_needed=10),
    )
    frames = [
        cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()
        for frame in random_board_views(distortion_maps(), 30, seed=5)
    ]
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(_hello(client="esp32-cam"))
        socket.send_text(_calibrate("start"))
        for index, jpeg in enumerate(frames):
            report = _send(socket, jpeg, 1000.0 + 50 * index)
            if report["calibration"]["state"] != "capturing":
                break
        # The next frame at this size is corrected with the new lens.
        after = _send(socket, frames[0], 9000.0)

    assert report["calibration"]["state"] == "done"
    assert report["calibration"]["views"] == 10
    assert report["calibration"]["rms_px"] < 1.0
    listing = client.get("/calibration").json()["lenses"]
    assert [entry["key"] for entry in listing] == ["esp32-cam||640x480"]
    assert listing[0]["rms_px"] == report["calibration"]["rms_px"]
    assert after["lens"]["rms_px"] == report["calibration"]["rms_px"]


# --- Calibrating over HTTP ----------------------------------------------


def test_http_start_needs_a_session(client: TestClient) -> None:
    assert client.post("/calibration", json={}).status_code == 404


def test_http_start_with_one_session(client: TestClient) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        _send(socket, _first_frame())
        response = client.post("/calibration", json={})
        report = _send(socket, _first_frame(), 1050.0)

    assert response.status_code == 200
    assert response.json()["calibration"]["state"] == "capturing"
    assert report["calibration"]["state"] == "capturing"


def test_http_start_by_address(client: TestClient) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        _send(socket, _first_frame())
        address = client.get("/sessions").json()["sessions"][0]["address"]
        assert (
            client.post("/calibration", json={"address": "10.9.9.9:1"}).status_code
            == 404
        )
        response = client.post("/calibration", json={"address": address})
        cancel = client.post(
            "/calibration", json={"address": address, "action": "cancel"}
        )

    assert response.status_code == 200
    assert cancel.json()["calibration"]["state"] == "cancelled"


def test_http_start_is_refused_when_ambiguous(client: TestClient) -> None:
    with (
        client.websocket_connect(FRAME_SOCKET_PATH) as first,
        client.websocket_connect(FRAME_SOCKET_PATH) as second,
    ):
        _send(first, _first_frame())
        _send(second, _first_frame())
        response = client.post("/calibration", json={})
        first_report = _send(first, _first_frame(), 1050.0)
        second_report = _send(second, _first_frame(), 1050.0)

    assert response.status_code == 409
    assert "calibration" not in first_report
    assert "calibration" not in second_report


def test_calibration_routes_require_the_token(store) -> None:
    app = create_app(
        backend_factory=FakeCursorBackend,
        config=ServerConfig(token="secret"),
        lens_store_factory=lambda: store,
    )
    with TestClient(app) as test_client:
        assert test_client.get("/calibration").status_code == 401
        assert test_client.post("/calibration", json={}).status_code == 401
