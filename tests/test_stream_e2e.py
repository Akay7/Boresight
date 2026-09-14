"""End-to-end over the WebSocket: fixture JPEGs in, cursor moves out.

The fixtures are JPEG because that is what the phone will stream, which
means a fixture file *is* a wire payload -- these tests send the bytes
down the socket unmodified, with only the 8-byte timestamp prefixed.

What is under test here is the transport, not the solver or the
pipeline; both already have their own decks. So the sharpest available
assertion is that the transport changes nothing at all: streaming a
sequence must report exactly the raw solved-position track that
replaying the same files from disk produces (see `_rounded_position`
for why "raw" -- aim smoothing sits below this, at the cursor backend,
and is timing-sensitive by design). A transport that quietly
re-encoded, resized or reordered would pass a tolerance-based check
against the manifest and fail this one.

Frames are sent synchronously -- send one, wait for its acknowledgement,
send the next. The drop policy makes a saturated stream
non-deterministic by design, so racing it here would test the scheduler.
Dropping is asserted directly instead, further down, by holding the
processor.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from boresight.inject import FakeCursorBackend
from boresight.marker_map import load_marker_map
from boresight.pipeline import (
    DEFAULT_CONFIG_PATH,
    AimPipeline,
    FrameOutcome,
    FrameResult,
    replay,
)
from boresight.server import FRAME_SOCKET_PATH, create_app
from boresight.stream import pack_frame

VIDEO_DIR = Path(__file__).parent / "fixtures" / "synthetic_video"
CLOSE_RANGE_DIR = Path(__file__).parent / "fixtures" / "close_range"

CLIENT_MS = 1000.0


def _manifest(fixture_dir: Path) -> dict:
    return json.loads((fixture_dir / "manifest.json").read_text())


def _frame_bytes(fixture_dir: Path, entry: dict) -> bytes:
    return (fixture_dir / entry["file"]).read_bytes()


@pytest.fixture
def backend() -> FakeCursorBackend:
    return FakeCursorBackend()


@pytest.fixture
def client(backend: FakeCursorBackend) -> TestClient:
    app = create_app(backend_factory=lambda: backend)
    with TestClient(app) as test_client:
        yield test_client


def _stream(client: TestClient, fixture_dir: Path, limit: int | None = None) -> list:
    """Send every frame of a fixture, one acknowledgement at a time."""
    manifest = _manifest(fixture_dir)
    entries = manifest["frames"][:limit]
    reports = []
    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        for entry in entries:
            socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(fixture_dir, entry)))
            reports.append(socket.receive_json())
    return reports


def _rounded_position(result: FrameResult) -> tuple[float, float] | None:
    """A `FrameResult`'s position, rounded the way the wire report is.

    The raw, pre-smoothing solve -- the same value the pipeline both
    reports over the wire and hands to the cursor backend, before
    `MarkerSourceController`'s `SmoothingCursorBackend` does anything to
    it. That split is what makes this a meaningful transport check
    post-smoothing: the wire report is unaffected by it.
    """
    if result.position is None:
        return None
    return (round(result.position[0], 5), round(result.position[1], 5))


# --- The transport is transparent ------------------------------------


def test_streaming_produces_the_same_track_as_replaying(client: TestClient) -> None:
    """Streaming and replaying must agree on the raw solved position
    reported for each frame -- what a client renders as the aim point --
    even though the position actually sent to the cursor backend now
    also passes through aim smoothing, which is timing-sensitive and so
    is not expected to reproduce identically between a live socket and
    a tight offline loop. See `_rounded_position`."""
    reports = _stream(client, VIDEO_DIR)

    reference = replay(
        VIDEO_DIR,
        AimPipeline(load_marker_map(DEFAULT_CONFIG_PATH), FakeCursorBackend()),
    )

    assert [(report["x"], report["y"]) for report in reports] == [
        _rounded_position(result) for result in reference
    ]
    assert len(reports) == len(_manifest(VIDEO_DIR)["frames"])


def test_every_streamed_frame_is_solved_and_reported(client: TestClient) -> None:
    reports = _stream(client, VIDEO_DIR)

    assert all(report["outcome"] == "solved" for report in reports)
    assert all(report["markers_detected"] == 8 for report in reports)
    assert [report["processed"] for report in reports] == list(
        range(1, len(reports) + 1)
    )


def test_the_client_timestamp_is_echoed_untouched(client: TestClient) -> None:
    """The server cannot compute round-trip time -- the two clocks share
    no epoch. It echoes, and the phone subtracts against its own clock."""
    reports = _stream(client, VIDEO_DIR, limit=2)

    assert all(report["client_ms"] == CLIENT_MS for report in reports)


# --- Frames with nothing to solve ------------------------------------


def test_an_unsolvable_frame_moves_nothing_and_keeps_the_connection(
    client: TestClient, backend: FakeCursorBackend
) -> None:
    manifest = _manifest(CLOSE_RANGE_DIR)
    blank = next(
        entry
        for entry in manifest["frames"]
        if entry["expected_markers_when_generated"] == 0
    )
    solvable = next(
        entry
        for entry in manifest["frames"]
        if entry["expected_markers_when_generated"] > 0
    )

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(CLOSE_RANGE_DIR, blank)))
        blank_report = socket.receive_json()
        assert blank_report["outcome"] == "no_markers"
        assert backend.calls == []

        # The connection survived, which is the other half of the claim.
        socket.send_bytes(
            pack_frame(CLIENT_MS, _frame_bytes(CLOSE_RANGE_DIR, solvable))
        )
        next_report = socket.receive_json()

    assert next_report["outcome"] == "solved"
    assert len(backend.calls) == 1


def test_a_dropout_after_a_solve_is_still_reported_as_unsolved(
    client: TestClient, backend: FakeCursorBackend
) -> None:
    """`aim-hold` re-sends the last solved position to the cursor backend
    through a brief dropout, but that is a cursor-backend-only effect --
    the wire report for the dropout frame must stay exactly what an
    unsolved frame reports without holding, with no position implied."""
    solvable = _manifest(VIDEO_DIR)["frames"][0]
    blank = next(
        entry
        for entry in _manifest(CLOSE_RANGE_DIR)["frames"]
        if entry["expected_markers_when_generated"] == 0
    )

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(VIDEO_DIR, solvable)))
        solved_report = socket.receive_json()
        socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(CLOSE_RANGE_DIR, blank)))
        dropout_report = socket.receive_json()

    assert solved_report["outcome"] == "solved"
    assert dropout_report["outcome"] == "no_markers"
    assert dropout_report["x"] is None
    assert dropout_report["y"] is None
    # The cursor backend, meanwhile, was privately re-sent the solved
    # position -- the held resend this test exists to confirm happened.
    assert len(backend.calls) == 2
    assert backend.calls[0] == pytest.approx(backend.calls[1], abs=1e-9)
    assert backend.calls[0] == pytest.approx(
        (solved_report["x"], solved_report["y"]), abs=1e-4
    )


# --- Malformed input --------------------------------------------------


def test_a_corrupt_payload_costs_one_frame_not_the_session(
    client: TestClient, backend: FakeCursorBackend
) -> None:
    """A single corrupt frame on a lossy Wi-Fi link should not
    disconnect the player."""
    entry = _manifest(VIDEO_DIR)["frames"][0]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_bytes(pack_frame(CLIENT_MS, b"this is not a jpeg"))
        corrupt = socket.receive_json()
        assert corrupt["failed"] == 1
        assert corrupt["processed"] == 0
        assert backend.calls == []

        socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(VIDEO_DIR, entry)))
        recovered = socket.receive_json()

    assert recovered["outcome"] == "solved"
    assert recovered["failed"] == 1
    assert len(backend.calls) == 1


def test_a_message_too_short_for_the_header_is_counted_and_survived(
    client: TestClient, backend: FakeCursorBackend
) -> None:
    entry = _manifest(VIDEO_DIR)["frames"][0]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_bytes(b"\x00\x01\x02")
        short = socket.receive_json()
        assert short["received"] == 1
        assert short["failed"] == 1

        socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(VIDEO_DIR, entry)))
        recovered = socket.receive_json()

    assert recovered["outcome"] == "solved"
    assert backend.calls != []


# --- Telemetry --------------------------------------------------------


def test_reported_counts_reconcile_against_frames_received(client: TestClient) -> None:
    entries = _manifest(VIDEO_DIR)["frames"][:3]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_bytes(b"\x00")  # under-length: fails
        socket.receive_json()
        socket.send_bytes(pack_frame(CLIENT_MS, b"not a jpeg"))  # decodes: fails
        socket.receive_json()
        for entry in entries:
            socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(VIDEO_DIR, entry)))
            report = socket.receive_json()

    assert report["received"] == len(entries) + 2
    assert report["processed"] == len(entries)
    assert report["failed"] == 2
    assert (
        report["processed"] + report["dropped"] + report["failed"]
        == (report["received"])
    )


def test_round_trip_time_reported_by_the_client_is_recorded(
    client: TestClient,
) -> None:
    entry = _manifest(VIDEO_DIR)["frames"][0]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(json.dumps({"type": "rtt", "ms": 42.5}))
        socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(VIDEO_DIR, entry)))
        report = socket.receive_json()

    assert report["round_trip_ms"] == 42.5


def test_malformed_control_text_is_ignored(client: TestClient) -> None:
    """Text messages are not frames and must not be able to break one."""
    entry = _manifest(VIDEO_DIR)["frames"][0]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text("{not json")
        socket.send_text(json.dumps({"type": "rtt"}))
        socket.send_text(json.dumps(["not", "an", "object"]))
        socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(VIDEO_DIR, entry)))
        report = socket.receive_json()

    assert report["outcome"] == "solved"
    assert report["received"] == 1  # text never counts as a frame


# --- Trigger ------------------------------------------------------------


def test_trigger_message_invokes_click_once(
    client: TestClient, backend: FakeCursorBackend
) -> None:
    entry = _manifest(VIDEO_DIR)["frames"][0]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(json.dumps({"type": "trigger"}))
        socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(VIDEO_DIR, entry)))
        socket.receive_json()

    assert backend.clicks == 1


def test_repeated_trigger_messages_invoke_click_repeatedly(
    client: TestClient, backend: FakeCursorBackend
) -> None:
    entry = _manifest(VIDEO_DIR)["frames"][0]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        for _ in range(3):
            socket.send_text(json.dumps({"type": "trigger"}))
        socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(VIDEO_DIR, entry)))
        socket.receive_json()

    assert backend.clicks == 3


def test_trigger_interleaved_with_frames_does_not_disturb_frame_handling(
    client: TestClient, backend: FakeCursorBackend
) -> None:
    entries = _manifest(VIDEO_DIR)["frames"][:3]
    marker_map = load_marker_map(DEFAULT_CONFIG_PATH)
    expected = replay(VIDEO_DIR, AimPipeline(marker_map, backend))[:3]
    backend.calls.clear()

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        reports = []
        for entry in entries:
            socket.send_text(json.dumps({"type": "trigger"}))
            socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(VIDEO_DIR, entry)))
            reports.append(socket.receive_json())

    assert [report["outcome"] for report in reports] == [
        result.outcome.value for result in expected
    ]
    # The reported position is the pipeline's raw solved position (what
    # a client renders as the aim point), not whatever the cursor
    # backend was asked to move to -- that split is what lets aim
    # smoothing exist without this being a smoothed-vs-raw comparison.
    assert [(report["x"], report["y"]) for report in reports] == [
        _rounded_position(result) for result in expected
    ]


def test_stats_report_trigger_count(
    client: TestClient, backend: FakeCursorBackend
) -> None:
    entry = _manifest(VIDEO_DIR)["frames"][0]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(json.dumps({"type": "trigger"}))
        socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(VIDEO_DIR, entry)))
        first = socket.receive_json()
        socket.send_text(json.dumps({"type": "trigger"}))
        socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(VIDEO_DIR, entry)))
        second = socket.receive_json()

    assert first["triggers"] == 1
    assert second["triggers"] == 2


class _HeldPipeline:
    """Stands in for the real pipeline and blocks inside `process_frame`.

    Lets the test hold the processor open while frames pile up behind
    it, which is the only way to observe the drop policy without racing
    the scheduler.
    """

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.seen: list[int] = []

    def process_frame(self, frame, *, debug: bool = False) -> FrameResult:
        # A cheap fingerprint that differs per fixture frame, so the
        # test can assert *which* frames survived, not merely how many.
        self.seen.append(int(frame.sum()))
        if not self.entered.is_set():
            self.entered.set()
            self.release.wait(timeout=5.0)
        return FrameResult(outcome=FrameOutcome.NO_MARKERS)


def test_a_backlog_is_dropped_down_to_its_newest_frame(client: TestClient) -> None:
    """Queueing would turn a throughput shortfall into unbounded lag: the
    cursor would follow where the player aimed seconds ago and never
    catch up. Dropping costs nothing, because the frame being discarded
    is strictly worse information than the one replacing it."""
    entries = _manifest(VIDEO_DIR)["frames"][:4]
    payloads = [_frame_bytes(VIDEO_DIR, entry) for entry in entries]
    held = _HeldPipeline()
    client.app.state.markers._pipeline = held

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_bytes(pack_frame(CLIENT_MS, payloads[0]))
        assert held.entered.wait(timeout=5.0), "processor never started the first frame"

        # These three arrive while the processor is held. The receiver
        # must keep accepting them rather than applying backpressure,
        # and the slot must keep only the last.
        for payload in payloads[1:]:
            socket.send_bytes(pack_frame(CLIENT_MS, payload))
        time.sleep(0.2)

        held.release.set()
        reports = [socket.receive_json(), socket.receive_json()]

    expected = [
        int(cv2.imdecode(np.frombuffer(p, np.uint8), cv2.IMREAD_COLOR).sum())
        for p in (payloads[0], payloads[3])
    ]
    assert held.seen == expected, "the surviving frames were not the first and newest"

    final = reports[-1]
    assert final["received"] == 4
    assert final["processed"] == 2
    assert final["dropped"] == 2
    assert final["failed"] == 0


def test_a_second_connection_starts_from_zero(
    client: TestClient, backend: FakeCursorBackend
) -> None:
    """Counters belong to the connection, not the server. A session that
    inherited the previous one's numbers would make every measurement
    taken on the phone meaningless after the first reconnect."""
    entries = _manifest(VIDEO_DIR)["frames"][:2]

    for _ in range(2):
        with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
            for entry in entries:
                socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(VIDEO_DIR, entry)))
                report = socket.receive_json()
        assert report["received"] == len(entries)
        assert report["processed"] == len(entries)

    # The cursor kept moving across both sessions; only the counts reset.
    assert len(backend.calls) == 2 * len(entries)


# --- Debug geometry -----------------------------------------------------


def _send_frame(socket, entry: dict) -> dict:
    socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(VIDEO_DIR, entry)))
    return socket.receive_json()


def test_a_session_that_never_asks_sees_no_debug_key(client: TestClient) -> None:
    """Absent, not null. A client written against the payload as it
    stands must not find a key it never asked for and start
    half-rendering an overlay from it."""
    entry = _manifest(VIDEO_DIR)["frames"][0]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        report = _send_frame(socket, entry)

    assert "debug" not in report
    assert report["outcome"] == "solved"


def test_debug_geometry_is_delivered_once_asked_for(client: TestClient) -> None:
    entry = _manifest(VIDEO_DIR)["frames"][0]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(json.dumps({"type": "debug", "enabled": True}))
        report = _send_frame(socket, entry)

    geometry = report["debug"]
    assert geometry["image_px"] == [1280, 720]
    assert geometry["markers"], "a solved frame saw markers"
    assert all(marker["mapped"] for marker in geometry["markers"])
    assert len(geometry["screen_quad_px"]) == 4
    assert len(geometry["cursor_px"]) == 2
    assert geometry["reprojection_max_px"] is not None


def test_the_drawn_cursor_agrees_with_the_reported_position(
    client: TestClient,
) -> None:
    """The end-to-end form of the check the overlay exists for: the
    emitted position, carried back into the image, must land on the
    frame centre the aim point was taken from."""
    entry = _manifest(VIDEO_DIR)["frames"][0]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(json.dumps({"type": "debug", "enabled": True}))
        report = _send_frame(socket, entry)

    assert report["outcome"] == "solved"
    cursor_x, cursor_y = report["debug"]["cursor_px"]
    assert (cursor_x, cursor_y) == pytest.approx((1280 / 2, 720 / 2), abs=1.0)


def test_debug_geometry_stops_when_turned_off(client: TestClient) -> None:
    entries = _manifest(VIDEO_DIR)["frames"][:2]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(json.dumps({"type": "debug", "enabled": True}))
        assert "debug" in _send_frame(socket, entries[0])

        socket.send_text(json.dumps({"type": "debug", "enabled": False}))
        assert "debug" not in _send_frame(socket, entries[1])


def test_an_unsolved_frame_carries_nothing_over(client: TestClient) -> None:
    """The overlay draws onto a live image. A frame that cannot solve
    must clear the projection rather than leave the last good one in
    place, or the drawing becomes confidently wrong."""
    blank = next(
        entry
        for entry in _manifest(CLOSE_RANGE_DIR)["frames"]
        if entry["expected_markers_when_generated"] == 0
    )
    solvable = _manifest(VIDEO_DIR)["frames"][0]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(json.dumps({"type": "debug", "enabled": True}))
        socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(VIDEO_DIR, solvable)))
        assert socket.receive_json()["debug"]["screen_quad_px"] is not None

        socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(CLOSE_RANGE_DIR, blank)))
        report = socket.receive_json()

    assert report["outcome"] != "solved"
    assert report["debug"]["screen_quad_px"] is None
    assert report["debug"]["cursor_px"] is None
    assert report["debug"]["reprojection_max_px"] is None


def test_a_corrupt_frame_reports_no_geometry(client: TestClient) -> None:
    entry = _manifest(VIDEO_DIR)["frames"][0]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(json.dumps({"type": "debug", "enabled": True}))
        socket.send_bytes(pack_frame(CLIENT_MS, _frame_bytes(VIDEO_DIR, entry)))
        assert socket.receive_json()["debug"] is not None

        socket.send_bytes(pack_frame(CLIENT_MS, b"not a jpeg"))
        report = socket.receive_json()

    assert report["outcome"] == "decode_failed"
    assert report["debug"] is None


def test_enabling_debug_on_one_session_does_not_affect_another(
    client: TestClient,
) -> None:
    """One `AimPipeline` serves every connection. If the debug flag were
    anywhere but on the session, one phone's overlay would change what
    another phone's frames compute."""
    entry = _manifest(VIDEO_DIR)["frames"][0]

    with client.websocket_connect(FRAME_SOCKET_PATH) as watcher:
        with client.websocket_connect(FRAME_SOCKET_PATH) as debugger:
            debugger.send_text(json.dumps({"type": "debug", "enabled": True}))
            assert "debug" in _send_frame(debugger, entry)

            plain = _send_frame(watcher, entry)

    assert "debug" not in plain
    assert plain["outcome"] == "solved"


def test_a_malformed_debug_message_leaves_the_setting_alone(
    client: TestClient,
) -> None:
    """Same posture as `rtt`: ignore what cannot be read. Guessing would
    start or stop a debug session nobody asked for."""
    entries = _manifest(VIDEO_DIR)["frames"][:2]

    with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
        socket.send_text(json.dumps({"type": "debug"}))  # no `enabled`
        socket.send_text(json.dumps({"type": "debug", "enabled": "yes"}))
        assert "debug" not in _send_frame(socket, entries[0])

        # Still switchable afterwards: the malformed messages changed
        # nothing rather than wedging the session.
        socket.send_text(json.dumps({"type": "debug", "enabled": True}))
        assert "debug" in _send_frame(socket, entries[1])

        socket.send_text(json.dumps({"type": "debug", "enabled": None}))
        assert "debug" in _send_frame(socket, entries[0])
