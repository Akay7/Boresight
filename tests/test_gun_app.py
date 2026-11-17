"""The gun end to end on an ordinary computer: the real capture, aim and
output paths, with recorded frames and a recording USB device."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from boresight.gun.app import Gun
from boresight.gun.config import GunConfig, Loaded, TuningConfig
from boresight.gun.fakes import FixtureCamera, RecordingSink, ScriptedTrigger
from boresight.gun.hid import HidGadgetBackend, pack_report, parse_report
from boresight.gun.led import State, StatusIndicator
from boresight.inject import FakeCursorBackend
from boresight.marker_map import load_marker_map
from boresight.pipeline import DEFAULT_CONFIG_PATH, AimPipeline, replay

FIXTURES = Path(__file__).parent / "fixtures"
VIDEO = FIXTURES / "synthetic_video"


def _loaded(**tuning) -> Loaded:
    tuning = {"smoothing": False, "hold_s": 0.0, **tuning}
    return Loaded(
        GunConfig(tuning=TuningConfig(**tuning)),
        load_marker_map(DEFAULT_CONFIG_PATH),
        None,
        None,
    )


def _gun(camera, trigger=None, **tuning):
    sink = RecordingSink()
    indicator = StatusIndicator(None)
    gun = Gun(
        _loaded(**tuning),
        camera,
        HidGadgetBackend(sink),
        trigger or ScriptedTrigger(),
        indicator,
    )
    return gun, sink, indicator


def test_recorded_frames_give_the_servers_positions() -> None:
    gun, sink, _ = _gun(FixtureCamera(VIDEO))

    assert gun.run(threading.Event()) == 0

    expected = [
        pack_report(*result.position, False)
        for result in replay(
            VIDEO,
            AimPipeline(load_marker_map(DEFAULT_CONFIG_PATH), FakeCursorBackend()),
        )
        if result.position is not None
    ]
    assert expected  # the fixture does solve
    assert sink.reports[: len(expected)] == expected


def test_frames_that_never_solve_emit_nothing(tmp_path) -> None:
    import json

    import cv2
    import numpy as np

    cv2.imwrite(str(tmp_path / "blank.png"), np.full((120, 160), 128, np.uint8))
    (tmp_path / "manifest.json").write_text(
        json.dumps({"frames": [{"file": "blank.png"}] * 3})
    )
    gun, sink, indicator = _gun(FixtureCamera(tmp_path))

    gun.run(threading.Event())

    assert sink.reports == []
    assert indicator.state is State.SEARCHING


class Endless:
    """A camera that returns one frame forever, at `interval` seconds."""

    lossless = False

    def __init__(self, interval=0.005) -> None:
        self._frame = FixtureCamera(VIDEO).grab()[0]
        self._interval = interval
        self.closed = False

    def grab(self):
        time.sleep(self._interval)
        return self._frame, None

    def close(self) -> None:
        self.closed = True


def _run_in_thread(gun):
    stop = threading.Event()
    result = []
    thread = threading.Thread(target=lambda: result.append(gun.run(stop)))
    thread.start()
    return stop, thread, result


def _wait_for(predicate, timeout=5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.005)


def _buttons(sink) -> list[bool]:
    states = [parse_report(r)[2] for r in sink.reports]
    return [s for i, s in enumerate(states) if i == 0 or s != states[i - 1]]


def test_press_and_release_with_bounce_send_one_down_and_one_up() -> None:
    trigger = ScriptedTrigger()
    gun, sink, _ = _gun(Endless(), trigger)
    stop, thread, _ = _run_in_thread(gun)
    _wait_for(lambda: gun.frames > 2)

    for level in (True, False, True, False, True):  # bounce on the way down
        trigger.level = level
        time.sleep(0.003)
    time.sleep(0.05)
    for level in (False, True, False, True, False):  # and on the way up
        trigger.level = level
        time.sleep(0.003)
    time.sleep(0.05)
    stop.set()
    thread.join(5)

    assert _buttons(sink) == [False, True, False]


def test_stopping_releases_a_held_button() -> None:
    trigger = ScriptedTrigger()
    gun, sink, _ = _gun(Endless(), trigger)
    stop, thread, _ = _run_in_thread(gun)
    trigger.level = True
    _wait_for(lambda: any(parse_report(r)[2] for r in sink.reports))

    stop.set()
    thread.join(5)

    assert parse_report(sink.reports[-1])[2] is False
    assert sink.closed


def test_a_failing_camera_releases_the_button_and_shows_the_error() -> None:
    class Dying(Endless):
        def __init__(self) -> None:
            super().__init__()
            self.grabs = 0

        def grab(self):
            self.grabs += 1
            if self.grabs > 5:
                raise RuntimeError("sensor fell off the ribbon")
            return super().grab()

    trigger = ScriptedTrigger()
    trigger.level = True
    camera = Dying()
    gun, sink, indicator = _gun(camera, trigger)

    code = gun.run(threading.Event())

    assert code == 1
    assert indicator.state is State.ERROR
    assert parse_report(sink.reports[-1])[2] is False
    assert camera.closed


def test_slow_processing_drops_frames_instead_of_lagging() -> None:
    gun, _, _ = _gun(Endless(interval=0.002))
    lags: list[float] = []
    real = gun.process

    def slow(frame, t):
        lags.append(time.monotonic() - t)
        time.sleep(0.05)
        return real(frame, t)

    gun.process = slow
    stop, thread, _ = _run_in_thread(gun)
    time.sleep(1.0)
    stop.set()
    thread.join(5)

    assert gun._slot.dropped > 20
    assert len(lags) >= 5
    # The frame handled is the newest, so the delay stays about one
    # processing time and does not grow with the session.
    assert max(lags) < 0.2


def test_the_command_replays_frames_and_prints_the_reports(capsys) -> None:
    from boresight.gun.__main__ import main

    assert main(["--emulate", str(VIDEO)]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines and all(line.startswith("x=") and "button=" in line for line in lines)


def test_a_bad_configuration_stops_before_anything_starts(tmp_path, caplog) -> None:
    from boresight.gun.__main__ import main

    config = tmp_path / "gun.toml"
    config.write_text("[pins]\ntrigger = 5\nled = 5\n")

    assert main(["--config", str(config), "--emulate", str(VIDEO)]) == 2
    assert "both on GPIO 5" in caplog.text


def test_the_descriptor_for_the_setup_script_is_the_one_the_backend_uses() -> None:
    import subprocess
    import sys

    from boresight.gun.hid import REPORT_DESCRIPTOR

    out = subprocess.run(
        [sys.executable, "-m", "boresight.gun", "--print-descriptor"],
        capture_output=True,
        check=True,
    ).stdout

    assert out == REPORT_DESCRIPTOR
