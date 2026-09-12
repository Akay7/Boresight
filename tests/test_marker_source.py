"""Switching marker sources, and the overlay process behind it.

Driven with stub children rather than a real overlay: the process
lifecycle, the geometry handshake and every failure path can be
exercised exactly and quickly, and none of it puts tags on the
developer's screen. What these cannot answer is whether the tags
actually appear -- that is what the manual tasks are for.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from boresight.inject import FakeCursorBackend
from boresight.layout_source import resolve_layout
from boresight.marker_source import (
    MarkerSource,
    MarkerSourceController,
    MarkerSourceError,
    _overlay_command,
)

PRINTED = resolve_layout("file")


def _stub(body: str) -> callable:
    """A launcher that runs `body` as the overlay instead of the real one."""
    recorded: list[list[str]] = []

    def launch(_command, **kwargs):
        recorded.append(_command)
        return subprocess.Popen([sys.executable, "-c", body], **kwargs)

    launch.commands = recorded
    return launch


REPORTS_1920 = (
    "import json,sys,time;"
    'print(json.dumps({"event":"overlay-ready","screen_px":[1920,1080],'
    '"tag_px":86,"inset_px":22}), flush=True);'
    "time.sleep(60)"
)
REFUSES = (
    "import sys;"
    'sys.stderr.write("this Wayland compositor does not support layer-shell");'
    "sys.exit(2)"
)
SILENT_EXIT = "import sys; sys.exit(3)"
HANGS = "import time; time.sleep(60)"


def _controller(body: str, **kwargs) -> MarkerSourceController:
    return MarkerSourceController(
        FakeCursorBackend(), PRINTED, launcher=_stub(body), **kwargs
    )


# --- Starting on printed markers --------------------------------------


def test_it_starts_on_printed_markers() -> None:
    controller = _controller(REPORTS_1920)

    state = controller.state()

    assert state["source"] == "printed"
    assert state["overlay_running"] is False
    assert state["screen_size"] == [1220.0, 686.0]


# --- Selecting on-screen markers --------------------------------------


def test_selecting_on_screen_markers_starts_the_overlay() -> None:
    controller = _controller(REPORTS_1920)
    try:
        state = controller.select(MarkerSource.SCREEN)

        assert state["source"] == "screen"
        assert state["overlay_running"] is True
        assert state["geometry"]["screen_px"] == [1920, 1080]
    finally:
        controller.shutdown()


def test_the_solved_layout_comes_from_what_the_overlay_reported() -> None:
    """Not from a configured resolution and not from a guess. This is
    what makes the drawn and solved layouts the same layout."""
    controller = _controller(REPORTS_1920)
    try:
        controller.select(MarkerSource.SCREEN)
        layout = controller.pipeline._map  # noqa: SLF001 - asserting on internals

        assert layout.screen_size_mm == (1920.0, 1080.0)
        assert layout.markers[0].size_mm == 86.0
        assert (layout.markers[0].x_mm, layout.markers[0].y_mm) == (22.0, 22.0)
    finally:
        controller.shutdown()


def test_switching_back_restores_the_printed_layout() -> None:
    controller = _controller(REPORTS_1920)
    try:
        controller.select(MarkerSource.SCREEN)
        state = controller.select(MarkerSource.PRINTED)

        assert state["source"] == "printed"
        assert state["overlay_running"] is False
        assert controller.pipeline._map == PRINTED  # noqa: SLF001
    finally:
        controller.shutdown()


def test_selecting_the_active_source_starts_nothing_new() -> None:
    """A double tap on the phone must not restart the overlay."""
    launcher = _stub(REPORTS_1920)
    controller = MarkerSourceController(FakeCursorBackend(), PRINTED, launcher=launcher)
    try:
        controller.select(MarkerSource.SCREEN)
        controller.select(MarkerSource.SCREEN)

        assert len(launcher.commands) == 1
    finally:
        controller.shutdown()


# --- Failure -----------------------------------------------------------


def test_a_refusing_overlay_leaves_printed_markers_active() -> None:
    """The failure this most protects against: a control saying 'on'
    while nothing is on screen, and a solver using a layout for tags
    that do not exist."""
    controller = _controller(REFUSES)

    with pytest.raises(MarkerSourceError, match="layer-shell"):
        controller.select(MarkerSource.SCREEN)

    state = controller.state()
    assert state["source"] == "printed"
    assert state["overlay_running"] is False
    assert "layer-shell" in state["error"]


def test_the_overlays_own_explanation_is_kept() -> None:
    controller = _controller(REFUSES)

    with pytest.raises(MarkerSourceError) as caught:
        controller.select(MarkerSource.SCREEN)

    assert "Wayland compositor" in str(caught.value)


def test_an_exit_without_explanation_still_reports_something() -> None:
    controller = _controller(SILENT_EXIT)

    with pytest.raises(MarkerSourceError, match="status 3"):
        controller.select(MarkerSource.SCREEN)


def test_an_overlay_that_never_reports_is_bounded_by_a_timeout(monkeypatch) -> None:
    """An unbounded read here would hang the request that asked for it."""
    monkeypatch.setattr("boresight.marker_source.GEOMETRY_TIMEOUT_S", 0.5)
    controller = _controller(HANGS)

    with pytest.raises(MarkerSourceError, match="did not report its geometry"):
        controller.select(MarkerSource.SCREEN)

    assert controller.state()["source"] == "printed"


def test_the_system_still_works_after_a_failed_selection() -> None:
    controller = _controller(REFUSES)
    with pytest.raises(MarkerSourceError):
        controller.select(MarkerSource.SCREEN)

    # Still solving, still selectable.
    assert controller.pipeline is not None
    assert controller.select(MarkerSource.PRINTED)["source"] == "printed"


# --- Liveness ----------------------------------------------------------


def test_an_overlay_that_dies_stops_being_claimed_as_active() -> None:
    controller = _controller(
        "import json,sys;"
        'print(json.dumps({"event":"overlay-ready","screen_px":[1920,1080],'
        '"tag_px":86,"inset_px":22}), flush=True);'
        "sys.exit(0)"
    )
    controller.select(MarkerSource.SCREEN)
    controller._process.wait(timeout=5)  # noqa: SLF001

    state = controller.state()

    assert state["source"] == "printed"
    assert state["overlay_running"] is False
    assert "exited on its own" in state["error"]


# --- Lifecycle ---------------------------------------------------------


def test_shutdown_terminates_the_overlay() -> None:
    """The overlay takes no input and has no title bar, so one that
    outlives the server cannot be dismissed by clicking."""
    controller = _controller(REPORTS_1920)
    controller.select(MarkerSource.SCREEN)
    process = controller._process  # noqa: SLF001

    controller.shutdown()

    assert process.poll() is not None
    assert controller.state()["overlay_running"] is False


def test_switching_to_printed_terminates_the_overlay() -> None:
    controller = _controller(REPORTS_1920)
    controller.select(MarkerSource.SCREEN)
    process = controller._process  # noqa: SLF001

    controller.select(MarkerSource.PRINTED)

    assert process.poll() is not None


def test_shutdown_is_safe_when_nothing_is_running() -> None:
    _controller(REPORTS_1920).shutdown()  # must not raise


# --- The command -------------------------------------------------------


def test_the_overlay_command_is_fixed() -> None:
    """Nothing from a request reaches this list."""
    assert _overlay_command(None) == [sys.executable, "-m", "boresight.overlay"]


def test_a_display_index_is_forced_through_int() -> None:
    """The only caller-supplied value in the command, and it cannot
    carry anything but a number."""
    assert _overlay_command(2)[-2:] == ["--display", "2"]

    with pytest.raises((ValueError, TypeError)):
        _overlay_command("1; rm -rf /")


def test_a_launcher_failure_is_reported_not_raised_raw() -> None:
    def refuse(*_args, **_kwargs):
        raise OSError("no such executable")

    controller = MarkerSourceController(FakeCursorBackend(), PRINTED, launcher=refuse)

    with pytest.raises(MarkerSourceError, match="could not start the overlay"):
        controller.select(MarkerSource.SCREEN)


def test_the_child_can_import_what_the_parent_is_running() -> None:
    """The parent imports `boresight` by construction -- it is running
    from it -- but the child is a fresh interpreter whose `-m` resolves
    against its own path. A server started as a script, from an odd
    working directory, or with the package reachable only via
    PYTHONPATH can leave the child unable to find it, and the symptom
    is a bare "No module named boresight.overlay" from a machine where
    the server is plainly working."""
    import boresight
    from boresight.marker_source import _overlay_environment

    package_parent = str(Path(boresight.__file__).resolve().parent.parent)
    first = _overlay_environment()["PYTHONPATH"].split(os.pathsep)[0]

    assert first == package_parent


def test_an_existing_pythonpath_is_kept(monkeypatch) -> None:
    monkeypatch.setenv("PYTHONPATH", "/somewhere/else")
    from boresight.marker_source import _overlay_environment

    entries = _overlay_environment()["PYTHONPATH"].split(os.pathsep)

    assert entries[-1] == "/somewhere/else"
    assert len(entries) == 2
