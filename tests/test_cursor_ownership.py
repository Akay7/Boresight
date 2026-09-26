"""Several sessions, one cursor: over real sockets, with real frames.

Session A aims with the first frame of the rendered fixture, session B
with a frame aimed somewhere else entirely, so whose aim reached the
cursor is visible in the recording backend's calls.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boresight.inject import FakeCursorBackend
from boresight.server import FRAME_SOCKET_PATH, create_app
from boresight.stream import pack_frame

VIDEO_DIR = Path(__file__).parent / "fixtures" / "synthetic_video"


def _frame(index: int) -> bytes:
    manifest = json.loads((VIDEO_DIR / "manifest.json").read_text())
    return (VIDEO_DIR / manifest["frames"][index]["file"]).read_bytes()


A_FRAME = _frame(0)
B_FRAME = _frame(12)


class _Shooter:
    """One socket, with its own client clock ticking 50 ms per frame."""

    def __init__(self, socket, frame: bytes, start_ms: float) -> None:
        self.socket = socket
        self.frame = frame
        self.client_ms = start_ms

    def aim(self) -> dict:
        self.client_ms += 50.0
        self.socket.send_bytes(pack_frame(self.client_ms, self.frame))
        report = self.socket.receive_json()
        assert report["outcome"] == "solved"
        return report

    def pull(self) -> None:
        self.socket.send_text(json.dumps({"type": "trigger"}))


@pytest.fixture
def backend() -> FakeCursorBackend:
    return FakeCursorBackend()


@pytest.fixture
def client(backend: FakeCursorBackend) -> TestClient:
    app = create_app(backend_factory=lambda: backend)
    with TestClient(app) as test_client:
        yield test_client


def test_a_second_session_does_not_move_the_cursor(
    client: TestClient, backend: FakeCursorBackend
) -> None:
    with (
        client.websocket_connect(FRAME_SOCKET_PATH) as first,
        client.websocket_connect(FRAME_SOCKET_PATH) as second,
    ):
        a = _Shooter(first, A_FRAME, 1000.0)
        b = _Shooter(second, B_FRAME, 9_000_000.0)
        a_report = a.aim()
        moves = len(backend.calls)
        b_report = b.aim()
        b_report = b.aim()

        assert len(backend.calls) == moves
        # B is still solved and told where it is aiming, just not obeyed.
        assert (b_report["x"], b_report["y"]) != (a_report["x"], a_report["y"])
        assert a_report["cursor"] == "yours"
        assert b_report["cursor"] == "other"


def test_pressing_the_trigger_takes_the_cursor(
    client: TestClient, backend: FakeCursorBackend
) -> None:
    with (
        client.websocket_connect(FRAME_SOCKET_PATH) as first,
        client.websocket_connect(FRAME_SOCKET_PATH) as second,
    ):
        a = _Shooter(first, A_FRAME, 1000.0)
        b = _Shooter(second, B_FRAME, 9_000_000.0)
        a.aim()
        b.aim()

        b.pull()
        b_report = b.aim()
        moves = len(backend.calls)
        a_report = a.aim()

        assert b_report["cursor"] == "yours"
        assert a_report["cursor"] == "other"
        assert len(backend.calls) == moves
        assert backend.clicks == 1


def test_a_disconnect_hands_the_cursor_over(
    client: TestClient, backend: FakeCursorBackend
) -> None:
    with client.websocket_connect(FRAME_SOCKET_PATH) as second:
        b = _Shooter(second, B_FRAME, 9_000_000.0)
        with client.websocket_connect(FRAME_SOCKET_PATH) as first:
            _Shooter(first, A_FRAME, 1000.0).aim()
            assert b.aim()["cursor"] == "other"

        # The first session's teardown runs as its socket closes.
        arbiter = client.app.state.arbiter
        deadline = time.monotonic() + 2.0
        while arbiter._owner is not None and time.monotonic() < deadline:  # noqa: SLF001
            time.sleep(0.01)
        moves = len(backend.calls)
        report = b.aim()

    assert report["cursor"] == "yours"
    assert len(backend.calls) == moves + 1


def test_a_handover_does_not_blend_the_two_streams(
    client: TestClient, backend: FakeCursorBackend
) -> None:
    """B aims at one steady point throughout. Smoothed by its own
    filter, that is exactly the point; a filter shared with A would put
    the cursor somewhere between A's aim and B's."""
    with (
        client.websocket_connect(FRAME_SOCKET_PATH) as first,
        client.websocket_connect(FRAME_SOCKET_PATH) as second,
    ):
        a = _Shooter(first, A_FRAME, 1000.0)
        b = _Shooter(second, B_FRAME, 9_000_000.0)
        for _ in range(3):
            a.aim()
            b_report = b.aim()

        b.pull()
        b.aim()

    assert backend.calls[-1] == pytest.approx((b_report["x"], b_report["y"]), abs=1e-4)
