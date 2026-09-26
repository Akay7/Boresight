"""Record and replay: a live session saved in the fixtures' own format.

The sharpest check available is the round trip. Stream a checked-in
fixture over the socket, save it, and replay the saved directory
through the same harness the fixtures go through: the track must be
exactly the one the original files give. Anything the recorder did to
the bytes, the order, or the layout would show up as a difference.

The buffer's own bounds are tested against an injected clock, so
eviction is asserted on the window and the cap directly rather than by
streaming for ten real seconds.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from boresight import pipeline
from boresight.detect import detect_markers
from boresight.inject import FakeCursorBackend
from boresight.marker_map import load_marker_map
from boresight.netaccess import ServerConfig
from boresight.pipeline import DEFAULT_CONFIG_PATH, AimPipeline, replay
from boresight.recording import (
    FrameRecorder,
    NothingToRecordError,
    RecordingConfig,
    recording_request,
    save_recording,
)
from boresight.server import FRAME_SOCKET_PATH, create_app
from boresight.solve import solve
from boresight.stream import pack_frame

VIDEO_DIR = Path(__file__).parent / "fixtures" / "synthetic_video"
TOKEN = "recording-test-token-5f2c9a"


def _fixture_frames(limit: int | None = None) -> list[bytes]:
    manifest = json.loads((VIDEO_DIR / "manifest.json").read_text())
    return [
        (VIDEO_DIR / entry["file"]).read_bytes() for entry in manifest["frames"][:limit]
    ]


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def layout():
    return load_marker_map(DEFAULT_CONFIG_PATH)


# --- The buffer --------------------------------------------------------


def test_frames_older_than_the_window_are_evicted(layout) -> None:
    clock = _Clock()
    recorder = FrameRecorder(RecordingConfig(seconds=1.0), clock=clock)
    for index in range(5):
        recorder.frame(float(index), b"x" * 10, layout)
        clock.now += 0.4

    frames = recorder.snapshot().frames
    # Snapshot at t=102.0: only frames received after 101.0 remain.
    assert [frame.client_ms for frame in frames] == [3.0, 4.0]


def test_the_byte_cap_evicts_before_the_window_does(layout) -> None:
    recorder = FrameRecorder(
        RecordingConfig(seconds=60.0, max_bytes=250), clock=_Clock()
    )
    for index in range(5):
        recorder.frame(float(index), b"x" * 100, layout)

    assert [frame.client_ms for frame in recorder.snapshot().frames] == [3.0, 4.0]
    assert recorder.retained_bytes == 200


def test_buffering_keeps_the_payload_object_itself(layout) -> None:
    payload = b"jpeg bytes"
    recorder = FrameRecorder(RecordingConfig())
    recorder.frame(1.0, payload, layout)
    assert recorder.snapshot().frames[0].payload is payload


def test_results_attach_to_their_frame(layout) -> None:
    recorder = FrameRecorder(RecordingConfig())
    recorder.frame(1.0, b"a", layout)
    recorder.frame(2.0, b"b", layout)
    recorder.result(2.0, "solved", (0.25, 0.75))

    first, second = recorder.snapshot().frames
    assert first.live is None
    assert second.live == {"outcome": "solved", "position": [0.25, 0.75]}


def test_control_keeps_parsed_fields_only(layout) -> None:
    recorder = FrameRecorder(RecordingConfig())
    recorder.control(
        json.dumps({"type": "trigger", "state": "down", "frame_ms": 12.5, "x": TOKEN})
    )
    recorder.control(json.dumps({"type": "trigger"}))
    recorder.control(json.dumps({"type": "rtt", "ms": 40, "note": TOKEN}))
    recorder.control(json.dumps({"type": "hello", "client": "phone", "extra": TOKEN}))
    recorder.control("not json")

    snapshot = recorder.snapshot()
    assert [(t["state"], t["frame_ms"]) for t in snapshot.triggers] == [
        ("down", 12.5),
        ("click", None),
    ]
    assert snapshot.client == {"client": "phone", "version": None, "frame_size": None}
    assert TOKEN not in repr(snapshot)


def test_only_a_record_message_is_a_record_request() -> None:
    assert recording_request('{"type": "record"}')
    assert not recording_request('{"type": "trigger", "state": "record"}')
    assert not recording_request('{"type": "rtt"}')
    assert not recording_request("record")
    assert not recording_request(None)


# --- Writing -----------------------------------------------------------


def test_saving_an_empty_buffer_writes_nothing(tmp_path: Path) -> None:
    recorder = FrameRecorder(RecordingConfig(root=tmp_path))
    with pytest.raises(NothingToRecordError):
        save_recording(recorder.snapshot())
    assert list(tmp_path.iterdir()) == []


def test_a_saved_recording_is_the_fixture_format(tmp_path: Path, layout) -> None:
    payloads = _fixture_frames(limit=3)
    recorder = FrameRecorder(RecordingConfig(root=tmp_path))
    for index, payload in enumerate(payloads):
        recorder.frame(1000.0 + index * 50, payload, layout)

    saved = save_recording(recorder.snapshot())

    assert saved.frames == 3
    manifest = json.loads((saved.path / "manifest.json").read_text())
    fixture = json.loads((VIDEO_DIR / "manifest.json").read_text())
    for key in ("image_size", "screen_size_mm", "marker_size_mm", "marker_layout_mm"):
        assert manifest[key] == fixture[key], key
    for entry, payload in zip(manifest["frames"], payloads, strict=True):
        assert (saved.path / entry["file"]).read_bytes() == payload
    assert [entry["client_ms"] for entry in manifest["frames"]] == [
        1000.0,
        1050.0,
        1100.0,
    ]
    assert load_marker_map(saved.path / "markers.toml") == layout


def test_two_saves_in_one_second_do_not_merge(tmp_path: Path, layout) -> None:
    recorder = FrameRecorder(RecordingConfig(root=tmp_path))
    recorder.frame(1.0, _fixture_frames(limit=1)[0], layout)
    first = save_recording(recorder.snapshot())
    second = save_recording(recorder.snapshot())
    assert first.path != second.path
    assert (second.path / "manifest.json").exists()


def test_frames_from_before_a_layout_switch_are_left_out(
    tmp_path: Path, layout
) -> None:
    other = load_marker_map(DEFAULT_CONFIG_PATH)
    payload = _fixture_frames(limit=1)[0]
    recorder = FrameRecorder(RecordingConfig(root=tmp_path))
    recorder.frame(1.0, payload, other)
    recorder.frame(2.0, payload, layout)
    recorder.frame(3.0, payload, layout)

    saved = save_recording(recorder.snapshot())
    manifest = json.loads((saved.path / "manifest.json").read_text())
    assert (saved.frames, saved.omitted) == (2, 1)
    assert manifest["recording"]["omitted_frames"] == 1
    assert [entry["client_ms"] for entry in manifest["frames"]] == [2.0, 3.0]


def test_aim_pipeline_exposes_its_layout(layout) -> None:
    assert AimPipeline(layout, FakeCursorBackend()).marker_map is layout


# --- Through the server ------------------------------------------------


def _app(tmp_path: Path, token: str | None = None, **recording):
    return create_app(
        backend_factory=FakeCursorBackend,
        config=ServerConfig(token=token),
        recording=RecordingConfig(root=tmp_path / "recordings", **recording),
    )


def _stream_and_record(socket, payloads: list[bytes]) -> dict:
    for index, payload in enumerate(payloads):
        socket.send_bytes(pack_frame(1000.0 + index * 50, payload))
        socket.receive_json()
    socket.send_text(json.dumps({"type": "trigger", "frame_ms": 1050.0}))
    socket.send_text(json.dumps({"type": "record"}))
    while True:
        message = socket.receive_json()
        if message["type"] == "recording":
            return message


def test_a_recording_replays_to_the_same_track(tmp_path: Path) -> None:
    """The round trip: stream, save, replay; identical to the original."""
    payloads = _fixture_frames()
    with TestClient(_app(tmp_path)) as client:
        with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
            socket.send_text(json.dumps({"type": "hello", "client": "phone"}))
            answer = _stream_and_record(socket, payloads)

    recorded = Path(answer["path"])
    assert answer["frames"] == len(payloads)
    assert recorded.parent == (tmp_path / "recordings").resolve()

    def track(directory: Path, config: Path) -> list:
        results = replay(
            directory, AimPipeline(load_marker_map(config), FakeCursorBackend())
        )
        return [(result.outcome, result.position) for result in results]

    assert track(recorded, recorded / "markers.toml") == track(
        VIDEO_DIR, DEFAULT_CONFIG_PATH
    )

    manifest = json.loads((recorded / "manifest.json").read_text())
    assert all(entry["live"]["outcome"] == "solved" for entry in manifest["frames"])
    assert manifest["triggers"][0]["state"] == "click"
    assert manifest["triggers"][0]["frame_ms"] == 1050.0
    assert manifest["recording"]["client"]["client"] == "phone"
    assert manifest["recording"]["marker_source"]["source"] == "printed"


def test_a_recording_solves_from_its_manifest_alone(tmp_path: Path) -> None:
    """What test_solve_video_e2e does with a fixture: detect and solve
    each frame using only the manifest's layout keys."""
    with TestClient(_app(tmp_path)) as client:
        with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
            answer = _stream_and_record(socket, _fixture_frames(limit=4))

    directory = Path(answer["path"])
    manifest = json.loads((directory / "manifest.json").read_text())
    size = manifest["marker_size_mm"]
    for entry in manifest["frames"]:
        image = cv2.imread(str(directory / entry["file"]), cv2.IMREAD_GRAYSCALE)
        correspondences = []
        for marker in detect_markers(image):
            x, y = manifest["marker_layout_mm"][str(marker.marker_id)]
            known = [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]
            correspondences += [
                (point, (float(corner[0]), float(corner[1])))
                for point, corner in zip(known, marker.corners, strict=True)
            ]
        result = solve(correspondences, tuple(manifest["image_size"]))
        assert np.all(np.isfinite(result.aim_point_mm))


def test_the_replay_cli_uses_the_recordings_layout(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    with TestClient(_app(tmp_path)) as client:
        with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
            answer = _stream_and_record(socket, _fixture_frames(limit=3))

    # A layout that maps none of the recorded tags: if the CLI read it
    # instead of the shipped one, nothing would solve.
    directory = Path(answer["path"])
    (directory / "markers.toml").write_text(
        "screen_width_mm = 100\nscreen_height_mm = 100\n\n"
        "[[marker]]\nid = 40\nx = 0\ny = 0\nsize_mm = 10\n"
    )
    assert pipeline.main([str(directory), "--dry-run"]) == 0
    assert "0/3 frames emitted" in capsys.readouterr().out

    pipeline.main([str(directory), "--dry-run", "--config", str(DEFAULT_CONFIG_PATH)])
    assert "3/3 frames emitted" in capsys.readouterr().out


def test_record_before_any_frame_is_refused(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
            socket.send_text(json.dumps({"type": "record"}))
            answer = socket.receive_json()
    assert answer["type"] == "recording"
    assert "no frames" in answer["error"]
    assert not (tmp_path / "recordings").exists() or not any(
        (tmp_path / "recordings").iterdir()
    )


def test_recording_disabled_keeps_nothing_and_says_so(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path, seconds=0)) as client:
        with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
            socket.send_bytes(pack_frame(1.0, _fixture_frames(limit=1)[0]))
            socket.receive_json()
            assert client.app.state.recorders == {}
            socket.send_text(json.dumps({"type": "record"}))
            answer = socket.receive_json()
        assert "disabled" in answer["error"]
        assert client.post("/recordings").status_code == 409
    assert not (tmp_path / "recordings").exists()


def test_the_http_endpoint_saves_live_sessions(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        assert client.post("/recordings").status_code == 409
        with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
            for payload in _fixture_frames(limit=2):
                socket.send_bytes(pack_frame(1.0, payload))
                socket.receive_json()
            response = client.post("/recordings")
        assert client.app.state.recorders == {}

    assert response.status_code == 200
    (entry,) = response.json()["recordings"]
    assert entry["frames"] == 2
    assert (Path(entry["path"]) / "manifest.json").exists()


def test_the_http_endpoint_requires_the_token(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path, token=TOKEN)) as client:
        assert client.post("/recordings").status_code == 401
    assert not (tmp_path / "recordings").exists()


def test_no_recorded_file_contains_the_token(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path, token=TOKEN)) as client:
        with client.websocket_connect(f"{FRAME_SOCKET_PATH}?token={TOKEN}") as socket:
            socket.send_text(json.dumps({"type": "hello", "client": "phone"}))
            answer = _stream_and_record(socket, _fixture_frames(limit=3))
        response = client.post(
            "/recordings", headers={"Authorization": f"Bearer {TOKEN}"}
        )
        assert response.status_code == 409  # the session has ended

    files = list(Path(answer["path"]).iterdir())
    assert files
    for path in files:
        assert TOKEN.encode() not in path.read_bytes(), path.name


def test_the_phone_page_has_a_save_control(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        page = client.get("/").text
        script = client.get("/capture.js").text
    assert 'id="record"' in page
    assert 'type: "record"' in script
    assert 'stats.type === "recording"' in script
