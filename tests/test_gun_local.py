"""The gun's local output, with no Pi, display or uinput device: the real
marker-source controller drives a stand-in overlay that reports what the
real one would draw, frames rendered from that drawing aim a recording
cursor, and the trigger and the overlay's death behave as specified."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from boresight.aim_hold import DEFAULT_HOLD_S
from boresight.gun.app import Gun
from boresight.gun.autostart import (
    ENTRY_NAME,
    entry_text,
    gun_command,
    remove_entry,
    restart_script,
    write_entry,
)
from boresight.gun.config import (
    ConfigError,
    GunConfig,
    Loaded,
    OverlayConfig,
    TuningConfig,
    load,
    parse_config,
)
from boresight.gun.fakes import FixtureCamera, LoopingCamera, ScriptedTrigger
from boresight.gun.led import StatusIndicator
from boresight.gun.local import run_local
from boresight.gun.standin_overlay import launcher_for
from boresight.inject import FakeCursorBackend
from boresight.overlay.qt_backend import plan_overlay
from boresight.pipeline import FrameOutcome, FrameResult

SCREEN = (1280, 720)
TARGET = (500.0, 300.0)

# --- 3.1 configuration -----------------------------------------------------


def test_the_output_defaults_to_usb() -> None:
    config = parse_config({})

    assert config.output == "usb"
    assert config.overlay == OverlayConfig()


def test_the_overlay_settings_override() -> None:
    config = parse_config(
        {
            "output": "local",
            "overlay": {
                "display": "HDMI-A-1",
                "extra_margin_px": 24,
                "picture_aspect": "4:3",
            },
        }
    )

    assert config.output == "local"
    assert config.overlay == OverlayConfig("HDMI-A-1", 24, "4:3")


def test_an_unknown_output_names_both() -> None:
    with pytest.raises(ConfigError) as raised:
        parse_config({"output": "hdmi"})

    assert "'usb'" in str(raised.value) and "'local'" in str(raised.value)


@pytest.mark.parametrize(
    "overlay",
    [{"picture_aspect": "4x3"}, {"extra_margin_px": -1}, {"margin": 4}],
)
def test_bad_overlay_settings_are_refused(overlay) -> None:
    with pytest.raises(ConfigError):
        parse_config({"overlay": overlay})


def test_the_local_output_ignores_a_layout_and_says_so(tmp_path, caplog) -> None:
    config = tmp_path / "gun.toml"
    config.write_text('output = "local"\nlayout = "/nowhere/markers.toml"\n')

    with caplog.at_level(logging.INFO, logger="boresight.gun.config"):
        loaded = load(config)

    assert loaded.marker_map is None
    assert any("ignored" in record.message for record in caplog.records)


def test_the_usb_output_still_reads_the_layout(tmp_path) -> None:
    config = tmp_path / "gun.toml"
    config.write_text('layout = "/nowhere/markers.toml"\n')

    with pytest.raises(ConfigError, match="marker layout"):
        load(config)


# --- 3.2 a supplied pipeline -----------------------------------------------


class RecordingPipeline:
    def __init__(self) -> None:
        self.frames: list[tuple[tuple[int, ...], float | None]] = []
        self.zero = "unset"

    def process_frame(self, frame, *, t=None, lens=None):
        self.frames.append((frame.shape, t))
        return FrameResult(outcome=FrameOutcome.NO_MARKERS)


def test_a_supplied_pipeline_is_the_one_used() -> None:
    video = Path(__file__).parent / "fixtures" / "synthetic_video"
    pipeline = RecordingPipeline()
    loaded = Loaded(GunConfig(), None, None, None)

    gun = Gun(
        loaded,
        FixtureCamera(video),
        FakeLocal(),
        ScriptedTrigger(),
        StatusIndicator(None),
        pipeline=pipeline,
    )

    assert gun.run(threading.Event()) == 0
    assert len(pipeline.frames) == 20
    assert pipeline.zero is None  # handed the configured zero (none)


class FakeLocal(FakeCursorBackend):
    def close(self) -> None:
        pass


# --- 3.3 the local output, wired ---------------------------------------------


def _camera_view(screen_image, target, camera=(1280, 960), scale=0.45):
    homography = (
        np.array([[1, 0, camera[0] / 2], [0, 1, camera[1] / 2], [0, 0, 1]], float)
        @ np.array([[scale, 0, 0], [0, scale, 0], [0.00005, 0, 1]], float)
        @ np.array([[1, 0, -target[0]], [0, 1, -target[1]], [0, 0, 1]], float)
    )
    return cv2.warpPerspective(screen_image, homography, camera, borderValue=90)


@pytest.fixture(scope="module")
def frames_dir(tmp_path_factory) -> Path:
    """Frames of a camera aimed at TARGET on a screen showing exactly what
    the overlay draws there by default, over mid-grey 'game'."""
    plan = plan_overlay(SCREEN, (0, 0, *SCREEN))
    screen = np.full((SCREEN[1], SCREEN[0]), 128, np.uint8)
    for x, y, width, height in plan.rectangles:
        screen[y : y + height, x : x + width] = plan.canvas[
            y : y + height, x : x + width
        ]
    folder = tmp_path_factory.mktemp("local_frames")
    cv2.imwrite(str(folder / "aim.png"), _camera_view(screen, TARGET))
    (folder / "manifest.json").write_text(
        json.dumps({"frames": [{"file": "aim.png"}] * 12})
    )
    return folder


def _loaded(**overlay) -> Loaded:
    return Loaded(
        GunConfig(
            output="local",
            overlay=OverlayConfig(**overlay),
            tuning=TuningConfig(hold_s=DEFAULT_HOLD_S),
        ),
        None,
        None,
        None,
    )


def test_the_aim_reaches_the_cursor(frames_dir) -> None:
    cursor = FakeCursorBackend()

    code = run_local(
        _loaded(),
        FixtureCamera(frames_dir),
        cursor,
        ScriptedTrigger(),
        StatusIndicator(None),
        threading.Event(),
        launcher=launcher_for(SCREEN),
    )

    assert code == 0
    assert len(cursor.calls) >= 10
    x, y = cursor.calls[-1]
    assert x == pytest.approx(TARGET[0] / SCREEN[0], abs=0.004)
    assert y == pytest.approx(TARGET[1] / SCREEN[1], abs=0.004)


def test_a_bounced_trigger_is_one_press_and_one_release(frames_dir) -> None:
    cursor = FakeCursorBackend()
    trigger = ScriptedTrigger()
    stop = threading.Event()

    def pull() -> None:
        while not cursor.calls and not stop.is_set():  # aiming first
            time.sleep(0.01)
        for level in [1, 0, 1, 0, 1]:
            trigger.level = bool(level)
            time.sleep(0.002)
        time.sleep(0.15)
        for level in [0, 1, 0, 1, 0]:
            trigger.level = bool(level)
            time.sleep(0.002)
        time.sleep(0.15)
        presses_seen.append((cursor.presses, cursor.releases))
        stop.set()

    presses_seen: list[tuple[int, int]] = []
    puller = threading.Thread(target=pull)
    puller.start()
    code = run_local(
        _loaded(),
        LoopingCamera(frames_dir),
        cursor,
        trigger,
        StatusIndicator(None),
        stop,
        launcher=launcher_for(SCREEN),
    )
    puller.join(timeout=10)

    assert code == 0
    assert presses_seen == [(1, 1)]
    # And stopping releases again, in case the button were still held.
    assert cursor.presses == 1 and cursor.releases == 2


def _launcher_running(body: str):
    def launch(command, **kwargs):
        return subprocess.Popen([sys.executable, "-c", body], **kwargs)

    return launch


def test_an_overlay_that_dies_stops_the_gun_and_lets_go(frames_dir, caplog) -> None:
    report = {
        "event": "overlay-ready",
        "screen_px": list(SCREEN),
        "tag_px": 58,
        "inset_px": 14,
    }
    dies = (
        f"import json,sys,time; print(json.dumps({report!r}), flush=True); "
        "time.sleep(1.0); sys.stderr.write('lost the display'); sys.exit(1)"
    )
    cursor = FakeCursorBackend()
    started = time.monotonic()

    with caplog.at_level(logging.ERROR, logger="boresight.gun.local"):
        code = run_local(
            _loaded(),
            LoopingCamera(frames_dir),
            cursor,
            ScriptedTrigger(),
            StatusIndicator(None),
            threading.Event(),
            launcher=_launcher_running(dies),
            watch_every_s=0.1,
        )

    assert code == 1
    assert time.monotonic() - started < 10
    assert cursor.releases >= 1  # let go on the way out
    assert any("markers are gone" in r.message for r in caplog.records)


def test_an_overlay_that_will_not_start_is_reported(frames_dir, caplog) -> None:
    refuses = (
        "import sys; sys.stderr.write('no desktop session: DISPLAY is unset'); "
        "sys.exit(2)"
    )
    cursor = FakeCursorBackend()

    with caplog.at_level(logging.ERROR, logger="boresight.gun.local"):
        code = run_local(
            _loaded(),
            FixtureCamera(frames_dir),
            cursor,
            ScriptedTrigger(),
            StatusIndicator(None),
            threading.Event(),
            launcher=_launcher_running(refuses),
        )

    assert code == 1
    assert cursor.calls == []
    assert any("DISPLAY is unset" in r.message for r in caplog.records)


def test_the_overlay_settings_reach_the_overlay(frames_dir) -> None:
    commands: list[list[str]] = []
    standin = launcher_for(SCREEN)

    def recording(command, **kwargs):
        commands.append(command)
        return standin(command, **kwargs)

    run_local(
        _loaded(extra_margin_px=12, picture_aspect="4:3"),
        FixtureCamera(frames_dir),
        FakeCursorBackend(),
        ScriptedTrigger(),
        StatusIndicator(None),
        threading.Event(),
        launcher=recording,
    )

    (command,) = commands
    assert "--picture-aspect=4:3" in command
    assert command[command.index("--extra-margin-px") + 1] == "12"


# --- 3.4 emulated, from the command line -----------------------------------


def test_the_command_emulates_the_local_output(frames_dir, tmp_path) -> None:
    config = tmp_path / "gun.toml"
    config.write_text('output = "local"\n')

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "boresight.gun",
            "--config",
            str(config),
            "--emulate",
            str(frames_dir),
            "--screen",
            "1280x720",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.startswith("x=")]
    assert len(lines) >= 10
    x, y = (float(part.split("=")[1]) for part in lines[-1].split())
    assert x == pytest.approx(TARGET[0] / SCREEN[0], abs=0.004)
    assert y == pytest.approx(TARGET[1] / SCREEN[1], abs=0.004)


# --- 3.5 autostart ------------------------------------------------------------


def test_the_entry_runs_this_python_with_this_config(tmp_path) -> None:
    config = tmp_path / "gun.toml"
    config.write_text("")

    path = write_entry(config, environ={"XDG_CONFIG_HOME": str(tmp_path / "cfg")})

    assert path == tmp_path / "cfg" / "autostart" / ENTRY_NAME
    text = path.read_text()
    assert text.startswith("[Desktop Entry]\nType=Application\n")
    exec_line = next(line for line in text.splitlines() if line.startswith("Exec="))
    assert exec_line.startswith('Exec=sh -c "until ')
    assert sys.executable in exec_line and str(config.resolve()) in exec_line
    assert "do sleep 2; done" in exec_line


def test_removing_the_entry(tmp_path) -> None:
    environ = {"XDG_CONFIG_HOME": str(tmp_path)}
    write_entry(None, environ=environ)
    (tmp_path / "autostart" / "other.desktop").write_text("[Desktop Entry]\n")

    assert remove_entry(environ) == tmp_path / "autostart" / ENTRY_NAME
    assert remove_entry(environ) is None
    assert [p.name for p in (tmp_path / "autostart").iterdir()] == ["other.desktop"]


def test_special_characters_are_quoted_for_a_desktop_entry() -> None:
    text = entry_text(["/opt/a $b/py", "--config", '/x/"q"%1.toml'])
    exec_line = next(line for line in text.splitlines() if line.startswith("Exec="))

    assert "\\$b" in exec_line and '\\"q\\"' in exec_line and "%%1" in exec_line


@pytest.mark.skipif(sys.platform == "win32", reason="the entry runs under sh")
def test_the_entry_restarts_after_failures_and_stops_after_success(tmp_path) -> None:
    counter = tmp_path / "runs"
    program = tmp_path / "flaky.py"
    program.write_text(
        "import pathlib, sys\n"
        f"p = pathlib.Path({str(counter)!r})\n"
        "n = int(p.read_text()) + 1 if p.exists() else 1\n"
        "p.write_text(str(n))\n"
        "sys.exit(0 if n >= 3 else 1)\n"
    )
    script = restart_script([sys.executable, str(program)], pause_s=0.05)

    subprocess.run(["sh", "-c", script], timeout=30, check=True)

    assert counter.read_text() == "3"


def test_the_gun_command_is_this_interpreter() -> None:
    assert gun_command(None) == [sys.executable, "-m", "boresight.gun"]


def test_the_autostart_flag_writes_and_removes(tmp_path) -> None:
    config = tmp_path / "gun.toml"
    config.write_text('output = "local"\n')
    environ = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "cfg")}

    def gun(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "boresight.gun", *args],
            capture_output=True,
            text=True,
            timeout=60,
            env={**environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
        )

    assert gun("--config", str(config), "--autostart").returncode == 0
    assert (tmp_path / "cfg" / "autostart" / ENTRY_NAME).exists()
    assert gun("--autostart", "remove").returncode == 0
    assert not (tmp_path / "cfg" / "autostart" / ENTRY_NAME).exists()
