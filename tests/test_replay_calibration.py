"""Replay applies the lens and zero a recording was made with.

A recording is for reproducing what the player saw, so its own
calibration is applied by default and `calibrated=False` gives the raw
camera aim. Fixture sequences carry no calibration and must replay
exactly as they always have.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from boresight import pipeline
from boresight.inject import FakeCursorBackend
from boresight.lens import LensModel
from boresight.marker_map import load_marker_map
from boresight.netaccess import ServerConfig
from boresight.pipeline import (
    DEFAULT_CONFIG_PATH,
    AimPipeline,
    FrameOutcome,
    replay,
    replay_calibration,
)
from boresight.recording import RecordingConfig
from boresight.server import FRAME_SOCKET_PATH, create_app
from boresight.stream import pack_frame
from boresight.zeroing import Zero, client_key

VIDEO_DIR = Path(__file__).parent / "fixtures" / "synthetic_video"
ZERO = Zero(offset=(0.03, -0.02))


def _pipeline() -> AimPipeline:
    return AimPipeline(load_marker_map(DEFAULT_CONFIG_PATH), FakeCursorBackend())


def _track(directory: Path, **kwargs) -> list:
    return [
        (result.outcome, result.position)
        for result in replay(directory, _pipeline(), **kwargs)
    ]


def _image_size() -> tuple[int, int]:
    manifest = json.loads((VIDEO_DIR / "manifest.json").read_text())
    width, height = manifest["image_size"]
    return int(width), int(height)


def _lens(size: tuple[int, int]) -> LensModel:
    width, height = size
    matrix = np.array(
        [[0.9 * width, 0.0, width / 2], [0.0, 0.9 * width, height / 2], [0, 0, 1.0]]
    )
    return LensModel(matrix, np.array([-0.2, 0.05, 0.0, 0.0, 0.0]), size)


def _with_session(tmp_path: Path, session: dict) -> Path:
    """The video fixture, as if a session with `session` had recorded it."""
    directory = tmp_path / "recording"
    shutil.copytree(VIDEO_DIR, directory)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["recording"] = {"session": session}
    manifest_path.write_text(json.dumps(manifest))
    return directory


def test_a_fixture_carries_no_calibration() -> None:
    manifest = json.loads((VIDEO_DIR / "manifest.json").read_text())
    calibration = replay_calibration(manifest)
    assert calibration.lens is None
    assert calibration.zero is None
    assert calibration.skipped == ()


def test_a_zeroed_recording_replays_to_the_zeroed_aim(tmp_path: Path) -> None:
    directory = _with_session(tmp_path, {"lens": None, "zero": ZERO.as_dict()})
    zeroed = replay(directory, _pipeline())
    raw = replay(directory, _pipeline(), calibrated=False)

    assert any(result.emitted for result in zeroed)
    for with_zero, without in zip(zeroed, raw, strict=True):
        if not with_zero.emitted:
            continue
        assert with_zero.aim_point_mm == pytest.approx(
            ZERO.aim_mm(without.sight), abs=1e-6
        )
        assert with_zero.position != without.position


def test_a_calibrated_recording_replays_with_its_lens(tmp_path: Path) -> None:
    lens = _lens(_image_size())
    directory = _with_session(tmp_path, {"lens": lens.as_dict(), "zero": None})
    track = _track(directory)

    assert [outcome for outcome, _ in track] == [
        outcome for outcome, _ in _track(VIDEO_DIR)
    ]
    assert track != _track(directory, calibrated=False)


def test_a_lens_for_another_frame_size_is_not_applied(tmp_path: Path) -> None:
    width, height = _image_size()
    lens = _lens((width * 2, height * 2))
    directory = _with_session(tmp_path, {"lens": lens.as_dict(), "zero": None})
    assert _track(directory) == _track(VIDEO_DIR)


def test_calibration_off_equals_the_raw_frames(tmp_path: Path) -> None:
    lens = _lens(_image_size())
    directory = _with_session(
        tmp_path, {"lens": lens.as_dict(), "zero": ZERO.as_dict()}
    )
    assert _track(directory, calibrated=False) == _track(VIDEO_DIR)


def test_unreadable_calibration_is_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    directory = _with_session(
        tmp_path, {"lens": {"camera_matrix": [1, 2]}, "zero": {"offset": "left"}}
    )
    manifest = json.loads((directory / "manifest.json").read_text())
    assert replay_calibration(manifest).skipped == ("lens", "zero")
    assert _track(directory) == _track(VIDEO_DIR)

    assert pipeline.main([str(directory), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "skipping the recording's lens" in out
    assert "skipping the recording's zero" in out


def test_the_cli_says_what_it_applied(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    directory = _with_session(tmp_path, {"lens": None, "zero": ZERO.as_dict()})
    pipeline.main([str(directory), "--dry-run"])
    assert "applying the recording's zero" in capsys.readouterr().out

    pipeline.main([str(directory), "--dry-run", "--no-calibration"])
    assert "applying" not in capsys.readouterr().out


def test_a_zeroed_sessions_recording_replays_to_its_live_aim(tmp_path: Path) -> None:
    """The round trip: a zeroed session streams, saves, and the replay
    of the saved directory puts every solved frame where the session
    put it live."""
    manifest = json.loads((VIDEO_DIR / "manifest.json").read_text())
    payloads = [
        (VIDEO_DIR / entry["file"]).read_bytes() for entry in manifest["frames"]
    ]
    app = create_app(
        backend_factory=FakeCursorBackend,
        config=ServerConfig(),
        recording=RecordingConfig(root=tmp_path / "recordings"),
    )
    with TestClient(app) as client:
        client.app.state.zeroing.store.put(client_key("gun-1", "phone"), ZERO)
        with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
            socket.send_text(
                json.dumps({"type": "hello", "client": "phone", "id": "gun-1"})
            )
            for index, payload in enumerate(payloads):
                socket.send_bytes(pack_frame(1000.0 + index * 50, payload))
                socket.receive_json()
            socket.send_text(json.dumps({"type": "record"}))
            while (answer := socket.receive_json())["type"] != "recording":
                pass

    directory = Path(answer["path"])
    saved = json.loads((directory / "manifest.json").read_text())
    assert saved["recording"]["session"]["zero"] == ZERO.as_dict()

    replayed = replay(directory, _pipeline())
    compared = 0
    for entry, result in zip(saved["frames"], replayed, strict=True):
        if entry["live"]["outcome"] != "solved":
            continue
        assert result.outcome is FrameOutcome.SOLVED
        assert result.position == pytest.approx(entry["live"]["position"], abs=1e-4)
        compared += 1
    assert compared > 0
