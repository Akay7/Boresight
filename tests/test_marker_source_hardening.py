"""The overlay process under load and under concurrency.

Two failures, neither of which shows up in a test that starts one
overlay at a time and lets it say little: an overlay that fills a pipe
nobody reads and freezes, and two concurrent switches that each start
an overlay. Stub children again (see test_marker_source.py), with the
timing made explicit so a regression presents as a failure, not a hang.
"""

from __future__ import annotations

import io
import subprocess
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

from boresight.inject import FakeCursorBackend
from boresight.layout_source import resolve_layout
from boresight.marker_source import (
    OUTPUT_LINE_CHARS,
    OUTPUT_TAIL_LINES,
    MarkerSource,
    MarkerSourceController,
    MarkerSourceError,
    _PipeDrain,
)
from boresight.netaccess import ServerConfig
from boresight.server import create_app

PRINTED = resolve_layout("file")

# Well past a Linux pipe's default 64 KiB capacity.
FLOOD_BYTES = 256 * 1024

GEOMETRY = (
    'print(json.dumps({"event":"overlay-ready","screen_px":[1920,1080],'
    '"tag_px":86,"inset_px":22}), flush=True);'
)


def _recording_launcher(body: str):
    """A launcher that runs `body`, and remembers every process."""
    processes: list[subprocess.Popen] = []
    launched = threading.Event()

    def launch(_command, **kwargs):
        process = subprocess.Popen([sys.executable, "-c", body], **kwargs)
        processes.append(process)
        launched.set()
        return process

    launch.processes = processes
    launch.launched = launched
    return launch


def _slow_reporter(delay_s: float) -> str:
    return f"import json,time;time.sleep({delay_s});" + GEOMETRY + "time.sleep(60)"


def _kill_all(processes) -> None:
    for process in processes:
        if process.poll() is None:
            process.kill()
            process.wait()


# --- Draining the pipes -------------------------------------------------


def test_a_chatty_overlay_is_not_blocked_by_its_own_output(tmp_path, monkeypatch):
    """The freeze this change exists for: far more than a pipe holds,
    on stderr before the geometry and on both pipes after it. Without
    continuous draining the child blocks mid-write -- before the
    geometry, the start times out; after it, `done` never appears."""
    monkeypatch.setattr("boresight.marker_source.GEOMETRY_TIMEOUT_S", 10.0)
    done = tmp_path / "done"
    body = (
        "import json,sys,time;"
        f"[sys.stderr.write('x' * 99 + '\\n') for _ in range({FLOOD_BYTES // 100})];"
        "sys.stderr.flush();"
        + GEOMETRY
        + f"[sys.stderr.write('y' * 99 + '\\n') for _ in range({FLOOD_BYTES // 100})];"
        f"[sys.stdout.write('z' * 99 + '\\n') for _ in range({FLOOD_BYTES // 100})];"
        "sys.stderr.flush();sys.stdout.flush();"
        f"open({str(done)!r}, 'w').close();"
        "time.sleep(60)"
    )
    launcher = _recording_launcher(body)
    controller = MarkerSourceController(FakeCursorBackend(), PRINTED, launcher=launcher)
    try:
        state = controller.select(MarkerSource.SCREEN)
        assert state["source"] == "screen"

        deadline = time.monotonic() + 10.0
        while not done.exists() and time.monotonic() < deadline:
            time.sleep(0.05)

        assert done.exists(), "the overlay blocked writing its output"
        assert controller.state()["overlay_running"] is True
    finally:
        controller.shutdown()
        _kill_all(launcher.processes)


def test_the_explanation_survives_a_flood_and_stays_bounded() -> None:
    body = (
        "import sys;"
        f"[sys.stderr.write('n' * 96 + '\\n') for _ in range({FLOOD_BYTES // 97})];"
        "sys.stderr.write('this compositor cannot host an overlay\\n');"
        "sys.exit(2)"
    )
    controller = MarkerSourceController(
        FakeCursorBackend(), PRINTED, launcher=_recording_launcher(body)
    )

    with pytest.raises(MarkerSourceError) as caught:
        controller.select(MarkerSource.SCREEN)

    message = str(caught.value)
    assert message.endswith("this compositor cannot host an overlay")
    assert len(message) <= OUTPUT_TAIL_LINES * (OUTPUT_LINE_CHARS + 1)
    assert controller.state()["source"] == "printed"


def test_the_drain_keeps_a_bounded_tail() -> None:
    lines = [f"line {i}\n" for i in range(OUTPUT_TAIL_LINES * 5)]
    long_line = "L" * (OUTPUT_LINE_CHARS * 3) + "\n"
    drain = _PipeDrain(io.StringIO("".join(lines) + long_line + "last\n"), "test")

    assert drain.first_line(1.0) == "line 0\n"
    drain.join(1.0)

    kept = drain.tail().split("\n")
    assert len(kept) == OUTPUT_TAIL_LINES
    assert all(len(line) <= OUTPUT_LINE_CHARS for line in kept)
    assert drain.last_line() == "last"


def test_the_drain_reports_eof_before_any_line() -> None:
    drain = _PipeDrain(io.StringIO(""), "test")

    assert drain.first_line(1.0) == ""


def test_an_overlay_that_dies_says_why(monkeypatch) -> None:
    body = (
        "import json,sys,time;"
        + GEOMETRY
        + "time.sleep(0.2);"
        + "sys.stderr.write('lost the display connection\\n');sys.exit(1)"
    )
    launcher = _recording_launcher(body)
    controller = MarkerSourceController(FakeCursorBackend(), PRINTED, launcher=launcher)
    controller.select(MarkerSource.SCREEN)
    launcher.processes[0].wait(timeout=5)
    controller._stderr.join(5)  # noqa: SLF001 - let the drain reach EOF

    state = controller.state()

    assert state["source"] == "printed"
    assert "exited on its own" in state["error"]
    assert "lost the display connection" in state["error"]


# --- Serializing switches ----------------------------------------------


def _run_concurrently(calls) -> list:
    """Run each call on its own thread, released together."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def run(index, call):
        barrier.wait()
        try:
            results[index] = call()
        except Exception as error:  # noqa: BLE001 - reported by the test
            results[index] = error

    threads = [
        threading.Thread(target=run, args=(i, call)) for i, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert not any(thread.is_alive() for thread in threads)
    return results


def test_concurrent_selections_start_exactly_one_overlay() -> None:
    """Two quick taps, or eight: one overlay, and every tap is told it
    is on screen."""
    launcher = _recording_launcher(_slow_reporter(0.3))
    controller = MarkerSourceController(FakeCursorBackend(), PRINTED, launcher=launcher)
    try:
        results = _run_concurrently(
            [lambda: controller.select(MarkerSource.SCREEN)] * 8
        )

        assert len(launcher.processes) == 1
        assert all(result["source"] == "screen" for result in results)
        assert controller.state()["overlay_running"] is True
    finally:
        controller.shutdown()
        _kill_all(launcher.processes)


def test_a_selection_and_a_margin_change_leave_one_overlay() -> None:
    launcher = _recording_launcher(_slow_reporter(0.2))
    controller = MarkerSourceController(FakeCursorBackend(), PRINTED, launcher=launcher)
    try:
        _run_concurrently(
            [
                lambda: controller.select(MarkerSource.SCREEN),
                lambda: controller.set_overlay_extra_margin_px(30),
                lambda: controller.select(MarkerSource.SCREEN),
                lambda: controller.set_overlay_extra_margin_px(60),
            ]
        )

        alive = [p for p in launcher.processes if p.poll() is None]
        assert alive == [controller._process]  # noqa: SLF001
    finally:
        controller.shutdown()
        _kill_all(launcher.processes)


def test_setting_the_margin_in_effect_does_not_restart() -> None:
    launcher = _recording_launcher(_slow_reporter(0))
    controller = MarkerSourceController(
        FakeCursorBackend(), PRINTED, launcher=launcher, overlay_extra_margin_px=40
    )
    try:
        controller.select(MarkerSource.SCREEN)

        state = controller.set_overlay_extra_margin_px(40)

        assert len(launcher.processes) == 1
        assert state["source"] == "screen"
    finally:
        controller.shutdown()
        _kill_all(launcher.processes)


def test_reading_the_state_does_not_wait_for_a_switch() -> None:
    launcher = _recording_launcher(_slow_reporter(3))
    controller = MarkerSourceController(FakeCursorBackend(), PRINTED, launcher=launcher)
    switch = threading.Thread(target=lambda: controller.select(MarkerSource.SCREEN))
    try:
        switch.start()
        assert launcher.launched.wait(5)

        started = time.monotonic()
        state = controller.state()

        assert time.monotonic() - started < 0.5
        assert state["switching"] is True
    finally:
        switch.join(10)
        controller.shutdown()
        _kill_all(launcher.processes)

    assert controller.state()["switching"] is False


# --- Shutdown against a switch -------------------------------------------


def test_shutdown_aborts_a_start_in_progress() -> None:
    """A Ctrl-C during an overlay start must not sit out the geometry
    timeout, and must not leave the half-started overlay behind."""
    launcher = _recording_launcher("import time; time.sleep(60)")
    controller = MarkerSourceController(FakeCursorBackend(), PRINTED, launcher=launcher)
    outcome: list = []

    def select() -> None:
        try:
            outcome.append(controller.select(MarkerSource.SCREEN))
        except MarkerSourceError as error:
            outcome.append(error)

    switch = threading.Thread(target=select)
    try:
        switch.start()
        assert launcher.launched.wait(5)

        started = time.monotonic()
        controller.shutdown()

        assert time.monotonic() - started < 5.0
        switch.join(5)
        assert isinstance(outcome[0], MarkerSourceError)
        assert "shutting down" in str(outcome[0])
        assert launcher.processes[0].poll() is not None
        assert controller.state()["source"] == "printed"
    finally:
        _kill_all(launcher.processes)


def test_nothing_starts_after_shutdown() -> None:
    launcher = _recording_launcher(_slow_reporter(0))
    controller = MarkerSourceController(FakeCursorBackend(), PRINTED, launcher=launcher)
    controller.shutdown()

    with pytest.raises(MarkerSourceError, match="shutting down"):
        controller.select(MarkerSource.SCREEN)

    assert launcher.processes == []
    # Printed markers only ever stop things, so they stay selectable.
    assert controller.select(MarkerSource.PRINTED)["source"] == "printed"


# --- Over HTTP ------------------------------------------------------------


def test_concurrent_requests_start_one_overlay() -> None:
    """The routes are plain `def`s run in the threadpool, so concurrent
    requests really are concurrent calls into the controller."""
    launcher = _recording_launcher(_slow_reporter(0.3))
    backend = FakeCursorBackend()
    app = create_app(backend_factory=lambda: backend, config=ServerConfig())
    with TestClient(app) as client:
        client.app.state.markers._launcher = launcher  # noqa: SLF001
        try:
            responses = _run_concurrently(
                [lambda: client.post("/markers/source", json={"source": "screen"})] * 4
            )

            assert [response.status_code for response in responses] == [200] * 4
            assert all(response.json()["source"] == "screen" for response in responses)
            assert len(launcher.processes) == 1
        finally:
            _kill_all(launcher.processes)
