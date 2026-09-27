"""Choosing the display the gun aims at.

Listing and pinning run desktop tools, so they are tested against a
scripted runner with the output those tools really print (captured on
KDE Plasma 6 under Wayland, and from xrandr's documented format). The
routes are tested with the fake backend, which lists two displays.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boresight.displays import (
    Display,
    DisplayError,
    choose,
    list_linux_displays,
    parse_kscreen,
    parse_xrandr,
    pin_linux_device,
)
from boresight.inject import FakeCursorBackend, Rect
from boresight.marker_source import MarkerSourceError
from boresight.server import create_app
from boresight.settings import (
    LiveSettings,
    Settings,
    ViewPreferences,
    resolve_settings,
)

KDE = {"WAYLAND_DISPLAY": "wayland-0", "XDG_CURRENT_DESKTOP": "KDE", "DISPLAY": ":0"}
X11 = {"DISPLAY": ":0", "XDG_CURRENT_DESKTOP": "XFCE"}
GNOME = {"WAYLAND_DISPLAY": "wayland-0", "XDG_CURRENT_DESKTOP": "GNOME"}

KSCREEN = json.dumps(
    {
        "outputs": [
            {
                "name": "eDP-1",
                "enabled": True,
                "connected": True,
                "pos": {"x": 0, "y": 0},
                "size": {"width": 2880, "height": 1800},
                "scale": 2,
                "priority": 1,
            },
            {
                "name": "HDMI-A-1",
                "enabled": True,
                "connected": True,
                "pos": {"x": 1440, "y": 0},
                "size": {"width": 1920, "height": 1080},
                "scale": 1,
                "priority": 2,
            },
            {
                "name": "DP-2",
                "enabled": False,
                "connected": True,
                "pos": {"x": 0, "y": 0},
                "size": {"width": 1920, "height": 1080},
                "scale": 1,
                "priority": 0,
            },
        ]
    }
)

XRANDR = (
    "Monitors: 2\n"
    " 0: +*HDMI-1 1920/527x1080/296+0+0  HDMI-1\n"
    " 1: +DP-1 1280/338x1024/270+-1280+56  DP-1\n"
)


class Script:
    """A runner answering each command from a table, recording calls."""

    def __init__(self, answers: dict[str, str]) -> None:
        self.answers = answers
        self.calls: list[list[str]] = []

    def __call__(self, command) -> str:
        self.calls.append(list(command))
        key = " ".join(command)
        for prefix, answer in self.answers.items():
            if key.startswith(prefix):
                return answer
        raise DisplayError(f"unexpected command: {key}")


# --- Listing -------------------------------------------------------------


def test_kscreen_lists_enabled_outputs_at_their_logical_size() -> None:
    assert parse_kscreen(KSCREEN) == [
        Display("eDP-1", Rect(0, 0, 1440, 900), primary=True),
        Display("HDMI-A-1", Rect(1440, 0, 1920, 1080)),
    ]


def test_xrandr_lists_monitors_with_negative_offsets() -> None:
    assert parse_xrandr(XRANDR) == [
        Display("HDMI-1", Rect(0, 0, 1920, 1080), primary=True),
        Display("DP-1", Rect(-1280, 56, 1280, 1024)),
    ]


def test_kde_lists_through_kscreen() -> None:
    runner = Script({"kscreen-doctor -j": KSCREEN})
    names = [d.name for d in list_linux_displays(runner, KDE)]
    assert names == ["eDP-1", "HDMI-A-1"]


def test_kde_falls_back_to_xrandr_without_kscreen() -> None:
    runner = Script({"xrandr --listmonitors": XRANDR})
    names = [d.name for d in list_linux_displays(runner, KDE)]
    assert names == ["HDMI-1", "DP-1"]


def test_a_garbled_kscreen_answer_is_an_error() -> None:
    with pytest.raises(DisplayError, match="kscreen-doctor"):
        parse_kscreen("not json")


# --- Choosing ------------------------------------------------------------


DISPLAYS = parse_kscreen(KSCREEN)


def test_an_empty_name_is_the_primary_display() -> None:
    assert choose(DISPLAYS, "").name == "eDP-1"


def test_a_name_picks_that_display() -> None:
    assert choose(DISPLAYS, "HDMI-A-1").rect == Rect(1440, 0, 1920, 1080)


def test_an_unknown_name_lists_the_ones_there_are() -> None:
    with pytest.raises(DisplayError, match="eDP-1, HDMI-A-1"):
        choose(DISPLAYS, "DP-9")


# --- Pinning on Linux ----------------------------------------------------


def _kwin(device_listed_after: int = 0) -> tuple:
    """KWin's D-Bus answers, listing the cursor device after N polls."""
    polls = {"count": 0}
    script = Script({})

    def answer(command) -> str:
        script.calls.append(list(command))
        key = " ".join(command)
        if key.endswith("devicesSysNames"):
            polls["count"] += 1
            if polls["count"] <= device_listed_after:
                return 'as 1 "event0"\n'
            return 'as 2 "event0" "event26"\n'
        if key.endswith("event0 org.kde.KWin.InputDevice name"):
            return 's "AT Translated Set 2 keyboard"\n'
        if key.endswith("event26 org.kde.KWin.InputDevice name"):
            return 's "boresight-cursor"\n'
        if "set-property" in key:
            return ""
        raise DisplayError(f"unexpected command: {key}")

    return answer, script


def test_kde_sets_the_cursor_devices_output_through_kwin() -> None:
    runner, script = _kwin()
    pin_linux_device("HDMI-A-1", runner=runner, environ=KDE, sleep=lambda _: None)
    assert script.calls[-1] == [
        "busctl",
        "--user",
        "set-property",
        "org.kde.KWin",
        "/org/kde/KWin/InputDevice/event26",
        "org.kde.KWin.InputDevice",
        "outputName",
        "s",
        "HDMI-A-1",
    ]


def test_kde_waits_for_kwin_to_see_a_new_device() -> None:
    runner, script = _kwin(device_listed_after=3)
    waits: list[float] = []
    pin_linux_device("HDMI-A-1", runner=runner, environ=KDE, sleep=waits.append)
    assert len(waits) == 3
    assert "set-property" in script.calls[-1]


def test_kde_gives_up_when_kwin_never_lists_the_device() -> None:
    runner, _ = _kwin(device_listed_after=10_000)
    with pytest.raises(DisplayError, match="KWin does not list"):
        pin_linux_device("HDMI-A-1", runner=runner, environ=KDE, sleep=lambda _: None)


def test_x11_maps_the_device_with_xinput() -> None:
    runner = Script({"xinput map-to-output": ""})
    pin_linux_device("DP-1", runner=runner, environ=X11)
    assert runner.calls == [["xinput", "map-to-output", "boresight-cursor", "DP-1"]]


def test_other_wayland_desktops_point_to_their_own_settings() -> None:
    runner = Script({})
    with pytest.raises(DisplayError, match="tablet settings"):
        pin_linux_device("DP-1", runner=runner, environ=GNOME)
    assert runner.calls == []


# --- Settings and routes -------------------------------------------------


def _app(backend: FakeCursorBackend, display: str = "", path: Path | None = None):
    settings = LiveSettings(Settings(view=ViewPreferences(display=display)), path=path)
    return create_app(backend_factory=lambda: backend, settings=settings)


def test_the_display_comes_from_the_file_and_the_flag(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[view]\ndisplay = "HDMI-A-1"\n')
    assert resolve_settings(path, env={}).startup.view.display == "HDMI-A-1"
    live = resolve_settings(path, env={}, cli={"view.display": "DP-1"})
    assert live.startup.view.display == "DP-1"


def test_no_display_chosen_leaves_the_cursor_alone() -> None:
    backend = FakeCursorBackend()
    with TestClient(_app(backend)):
        assert backend.display is None


def test_a_saved_display_is_applied_at_startup() -> None:
    backend = FakeCursorBackend()
    with TestClient(_app(backend, "FAKE-2")):
        assert backend.display.name == "FAKE-2"


def test_an_unknown_saved_display_refuses_to_start() -> None:
    with pytest.raises(RuntimeError, match="FAKE-9"):
        with TestClient(_app(FakeCursorBackend(), "FAKE-9")):
            pass


def test_displays_are_listed_with_the_one_in_effect() -> None:
    with TestClient(_app(FakeCursorBackend(), "FAKE-2")) as client:
        state = client.get("/displays").json()
    assert state["selected"] == "FAKE-2"
    assert [d["name"] for d in state["displays"]] == ["FAKE-1", "FAKE-2"]
    assert state["displays"][1] == {
        "name": "FAKE-2",
        "x": 1920,
        "y": 0,
        "width": 1280,
        "height": 1024,
        "primary": False,
    }


def test_choosing_a_display_moves_the_cursor_and_is_saved(tmp_path: Path) -> None:
    backend = FakeCursorBackend()
    path = tmp_path / "config.toml"
    with TestClient(_app(backend, path=path)) as client:
        state = client.post("/display", json={"name": "FAKE-2"}).json()
        assert state["selected"] == "FAKE-2"
        assert backend.display.name == "FAKE-2"
        assert client.app.state.markers.display == "FAKE-2"
        client.post("/settings/save")
    assert tomllib.loads(path.read_text())["view"]["display"] == "FAKE-2"


def test_an_unknown_display_is_refused_and_changes_nothing() -> None:
    backend = FakeCursorBackend()
    with TestClient(_app(backend, "FAKE-2")) as client:
        answer = client.post("/display", json={"name": "FAKE-9"})
    assert answer.status_code == 409
    assert "FAKE-1, FAKE-2" in answer.json()["detail"]
    assert answer.json()["selected"] == "FAKE-2"
    assert backend.display.name == "FAKE-2"


def test_an_overlay_that_fails_on_the_new_display_is_reported(monkeypatch) -> None:
    backend = FakeCursorBackend()
    with TestClient(_app(backend)) as client:

        def fail(display: str) -> dict:
            raise MarkerSourceError("no overlay on that display")

        monkeypatch.setattr(client.app.state.markers, "set_display", fail)
        answer = client.post("/display", json={"name": "FAKE-2"})
    assert answer.status_code == 409
    assert "no overlay" in answer.json()["detail"]


def test_a_backend_without_displays_says_so() -> None:
    class Plain:
        """A backend with movement and buttons but no idea of displays."""

        def move_absolute(self, x: float, y: float) -> None: ...
        def click(self) -> None: ...
        def press(self) -> None: ...
        def release(self) -> None: ...

    with TestClient(_app(Plain())) as client:
        assert "no displays" in client.get("/displays").json()["detail"]
        assert client.post("/display", json={"name": ""}).status_code == 409


def test_the_page_carries_the_display_picker() -> None:
    with TestClient(_app(FakeCursorBackend())) as client:
        page = client.get("/").text
        script = client.get("/capture.js").text

    assert 'id="display-select"' in page
    for path in ('"displays"', '"display"'):
        assert f"sameOriginUrl({path})" in script
