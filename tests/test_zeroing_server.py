"""Zeroing over real sockets: shots that never click, and zeroes applied."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from boresight.inject import FakeCursorBackend
from boresight.server import FRAME_SOCKET_PATH, create_app
from boresight.stream import pack_frame
from boresight.zeroing import Zero

VIDEO_DIR = Path(__file__).parent / "fixtures" / "synthetic_video"
_MANIFEST = json.loads((VIDEO_DIR / "manifest.json").read_text())
SOLVABLE = (VIDEO_DIR / _MANIFEST["frames"][0]["file"]).read_bytes()
BLANK = cv2.imencode(".jpg", np.zeros((720, 1280, 3), np.uint8))[1].tobytes()


class _Client:
    def __init__(self, socket, client_id: str | None = None) -> None:
        self.socket = socket
        self.client_ms = 1000.0
        hello = {"type": "hello", "client": "phone"}
        if client_id is not None:
            hello["id"] = client_id
        socket.send_text(json.dumps(hello))

    def frame(self, jpeg: bytes = SOLVABLE) -> dict:
        self.client_ms += 50.0
        self.socket.send_bytes(pack_frame(self.client_ms, jpeg))
        return self.socket.receive_json()

    def zeroing(self, action: str) -> dict:
        self.socket.send_text(json.dumps({"type": "zeroing", "action": action}))
        return self.frame()["zeroing"]

    def shoot(self) -> None:
        down = {"type": "trigger", "state": "down", "frame_ms": self.client_ms}
        self.socket.send_text(json.dumps(down))
        self.socket.send_text(json.dumps({"type": "trigger", "state": "up"}))


@pytest.fixture
def backend() -> FakeCursorBackend:
    return FakeCursorBackend()


@pytest.fixture
def client(backend: FakeCursorBackend, tmp_path) -> TestClient:
    app = create_app(
        backend_factory=lambda: backend, zeroing_path=tmp_path / "zeroing.json"
    )
    with TestClient(app) as test_client:
        yield test_client


def test_every_report_carries_the_zeroing_state(client: TestClient) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        state = _Client(socket).frame()["zeroing"]

    assert state["active"] is False and state["zeroed"] is False
    assert state["target"] is None


def test_shots_while_zeroing_never_click(
    client: TestClient, backend: FakeCursorBackend
) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        phone = _Client(socket, "phone-1")
        phone.frame()
        state = phone.zeroing("start")
        assert state["active"] and state["target"]["index"] == 0
        assert state["target"]["count"] == 5
        assert "corner" in state["target"]["label"]

        phone.shoot()
        state = phone.frame()["zeroing"]
        assert state["shots"] == 1 and state["target"]["index"] == 1

        for _ in range(4):
            phone.shoot()
            report = phone.frame()
        state = report["zeroing"]

        assert (backend.clicks, backend.presses) == (0, 0)
        assert report["triggers"] == 0
        assert state["active"] is False and state["zeroed"] is True
        assert client.app.state.zeroing.store.get("phone-1").shots == 5

        # Zeroed: the trigger is a trigger again.
        phone.shoot()
        phone.frame()
        assert backend.presses == 1


def test_a_shot_on_a_frame_that_did_not_solve_is_a_miss(
    client: TestClient, backend: FakeCursorBackend
) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        phone = _Client(socket)
        phone.zeroing("start")
        # Past the 100 ms a solved neighbour may stand in for the shot.
        for _ in range(3):
            phone.frame(BLANK)
        phone.shoot()
        state = phone.frame(BLANK)["zeroing"]

    assert state["shots"] == 0 and "missed" in state["message"]
    assert backend.presses == 0


def test_a_stored_zero_is_applied_after_hello(client: TestClient) -> None:
    client.app.state.zeroing.store.put("zeroed", Zero(offset=(0.05, 0.0)))

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        plain = _Client(socket, "someone-else").frame()
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        zeroed = _Client(socket, "zeroed").frame()

    assert zeroed["zeroing"]["zeroed"] is True
    assert zeroed["x"] > plain["x"] + 0.01
    assert zeroed["y"] == pytest.approx(plain["y"], abs=0.005)


def test_reset_returns_to_the_raw_aim(client: TestClient) -> None:
    client.app.state.zeroing.store.put("zeroed", Zero(offset=(0.05, 0.0)))

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        phone = _Client(socket, "zeroed")
        before = phone.frame()
        state = phone.zeroing("reset")
        after = phone.frame()

    assert state["zeroed"] is False
    assert after["x"] < before["x"] - 0.01
    assert client.app.state.zeroing.store.get("zeroed") is None


def test_one_client_zeroes_at_a_time_and_leaving_frees_it(client: TestClient) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as first_socket:
        first = _Client(first_socket, "a")
        first.zeroing("start")
        with client.websocket_connect(FRAME_SOCKET_PATH) as second_socket:
            second = _Client(second_socket, "b")
            refused = second.zeroing("start")
            assert refused["active"] is False
            assert "another client" in refused["message"]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        assert _Client(socket, "b").zeroing("start")["active"] is True


def test_a_zero_survives_a_restart(backend: FakeCursorBackend, tmp_path) -> None:
    path = tmp_path / "zeroing.json"

    def run(action_count: int) -> dict:
        app = create_app(backend_factory=lambda: backend, zeroing_path=path)
        with (
            TestClient(app) as test_client,
            test_client.websocket_connect(FRAME_SOCKET_PATH) as socket,
        ):
            phone = _Client(socket, "phone-1")
            phone.frame()
            if action_count:
                phone.zeroing("start")
                phone.shoot()
                phone.frame()
                return phone.zeroing("finish")
            return phone.frame()["zeroing"]

    assert run(1)["zeroed"] is True
    assert run(0)["zeroed"] is True


def test_the_page_loads_the_zeroing_script(client: TestClient) -> None:
    page = client.get("/").text
    script = client.get("/zeroing.js")

    assert '<script src="zeroing.js"></script>' in page
    assert 'id="zeroing-start"' in page
    assert script.status_code == 200
    assert '"zeroing"' in script.text
    # The phone names itself, so its zero can be found again.
    assert "message.id = id" in client.get("/capture.js").text
