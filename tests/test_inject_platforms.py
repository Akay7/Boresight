"""The Windows and macOS cursor backends, against recording fakes.

Neither backend can send real input here, so each is handed a fake of
its thin platform layer (`Win32Api`, `QuartzApi`) and the tests assert
on exactly what it was asked to send: structure layouts, coordinate
normalisation and button sequences. The real layers get a smoke test
on their own platform only, and send nothing.
"""

from __future__ import annotations

import ctypes
import sys

import pytest

from boresight import inject
from boresight.inject import (
    CursorBackendUnavailable,
    Rect,
    cursor_rect_override,
    default_cursor_backend,
)
from boresight.inject_darwin import (
    ACCESSIBILITY_HINT,
    CGPoint,
    CGRect,
    QuartzCursorBackend,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseDragged,
    kCGEventLeftMouseUp,
    kCGEventMouseMoved,
    kCGMouseEventClickState,
    kCGMouseEventDeltaX,
    kCGMouseEventDeltaY,
)
from boresight.inject_win32 import (
    INPUT,
    INPUT_MOUSE,
    MOUSEEVENTF_ABSOLUTE,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    MOUSEEVENTF_MOVE,
    MOUSEEVENTF_VIRTUALDESK,
    MOUSEINPUT,
    Win32CursorBackend,
    to_absolute,
)

ABSOLUTE_MOVE = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK


@pytest.fixture(autouse=True)
def no_environment_overrides(monkeypatch):
    monkeypatch.delenv("BORESIGHT_CURSOR_RECT", raising=False)


PRIMARY = Rect(0, 0, 1920, 1080)
MAIN_DISPLAY = Rect(0, 0, 1440, 900)


def windows_pixel(n: int, origin: int, size: int) -> int:
    """Windows' own absolute-to-pixel conversion, which truncates."""
    return origin + n * size // 65536


# -- shared ------------------------------------------------------------


def test_rect_maps_the_unit_square_onto_first_and_last_pixel() -> None:
    rect = Rect(100, 50, 1920, 1080)
    assert rect.point(0.0, 0.0) == (100, 50)
    assert rect.point(1.0, 1.0) == (100 + 1919, 50 + 1079)


def test_cursor_rect_unset_is_none() -> None:
    assert cursor_rect_override({}) is None


def test_cursor_rect_parses_x_y_width_height() -> None:
    rect = cursor_rect_override({"BORESIGHT_CURSOR_RECT": "-1280,0,1280,1024"})
    assert rect == Rect(-1280, 0, 1280, 1024)


@pytest.mark.parametrize("raw", ["wide", "1,2,3", "0,0,0,100", "0,0,nan,100"])
def test_a_malformed_cursor_rect_names_the_expected_form(raw: str) -> None:
    with pytest.raises(CursorBackendUnavailable, match="x,y,width,height"):
        cursor_rect_override({"BORESIGHT_CURSOR_RECT": raw})


@pytest.mark.parametrize(
    ("platform", "module", "name"),
    [
        ("win32", "boresight.inject_win32", "Win32CursorBackend"),
        ("darwin", "boresight.inject_darwin", "QuartzCursorBackend"),
    ],
)
def test_the_default_backend_follows_the_platform(
    monkeypatch, platform: str, module: str, name: str
) -> None:
    sentinel = object()
    monkeypatch.setattr(f"{module}.{name}", lambda: sentinel)
    assert default_cursor_backend(platform) is sentinel


def test_linux_gets_the_uinput_backend(monkeypatch) -> None:
    sentinel = object()
    monkeypatch.setattr(inject, "UinputCursorBackend", lambda: sentinel)
    assert default_cursor_backend("linux") is sentinel


def test_an_unknown_platform_fails_naming_it() -> None:
    with pytest.raises(CursorBackendUnavailable, match="freebsd14"):
        default_cursor_backend("freebsd14")


# -- Windows -----------------------------------------------------------


class FakeWin32Api:
    def __init__(
        self,
        primary: Rect = PRIMARY,
        desktop: Rect | None = None,
        accept: bool = True,
    ) -> None:
        self.primary = primary
        self.desktop = desktop or primary
        self.accept = accept
        self.dpi_aware = False
        self.metrics_read_before_dpi = False
        self.batches: list[list[tuple[int, int, int]]] = []

    def make_dpi_aware(self) -> None:
        self.dpi_aware = True

    def primary_screen(self) -> Rect:
        self.metrics_read_before_dpi |= not self.dpi_aware
        return self.primary

    def virtual_screen(self) -> Rect:
        self.metrics_read_before_dpi |= not self.dpi_aware
        return self.desktop

    def send_input(self, inputs) -> int:
        for item in inputs:
            assert item.type == INPUT_MOUSE
        self.batches.append([(i.mi.dwFlags, i.mi.dx, i.mi.dy) for i in inputs])
        return len(inputs) if self.accept else 0

    @property
    def events(self) -> list[tuple[int, int, int]]:
        return [event for batch in self.batches for event in batch]


def test_input_has_the_windows_layout() -> None:
    # 64-bit: 4-byte type, 4 padding, 32-byte MOUSEINPUT (the 8-byte
    # dwExtraInfo aligned to 8). 32-bit: 4 + 24. SendInput rejects a
    # wrong cbSize outright, so this is the size that matters.
    pointer = ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(INPUT) == (40 if pointer == 8 else 28)
    assert ctypes.sizeof(MOUSEINPUT) == (32 if pointer == 8 else 24)
    assert INPUT.u.offset == (8 if pointer == 8 else 4)
    assert MOUSEINPUT.dwFlags.offset == 12
    assert MOUSEINPUT.dwExtraInfo.offset == (24 if pointer == 8 else 20)


@pytest.mark.parametrize(
    ("origin", "size"), [(0, 1920), (0, 1366), (-1280, 3200), (0, 7), (0, 65536)]
)
def test_every_pixel_round_trips_through_windows_conversion(
    origin: int, size: int
) -> None:
    for pixel in range(origin, origin + size):
        n = to_absolute(pixel, origin, size)
        assert 0 <= n <= 65535
        assert windows_pixel(n, origin, size) == pixel


def test_a_move_is_one_absolute_virtual_desktop_input() -> None:
    api = FakeWin32Api()
    backend = Win32CursorBackend(api)

    backend.move_absolute(0.5, 0.25)

    ((flags, dx, dy),) = api.events
    assert flags == ABSOLUTE_MOVE
    assert windows_pixel(dx, 0, 1920) == round(0.5 * 1919)
    assert windows_pixel(dy, 0, 1080) == round(0.25 * 1079)


def test_dpi_awareness_comes_before_any_metric() -> None:
    api = FakeWin32Api()
    Win32CursorBackend(api)
    assert api.dpi_aware
    assert not api.metrics_read_before_dpi


def test_the_primary_monitor_is_the_default_target_on_a_wider_desktop() -> None:
    # Primary 1920x1080 at the origin, a second monitor to its left.
    desktop = Rect(-1280, 0, 3200, 1080)
    api = FakeWin32Api(primary=Rect(0, 0, 1920, 1080), desktop=desktop)
    backend = Win32CursorBackend(api)

    backend.move_absolute(0.0, 0.0)
    backend.move_absolute(1.0, 1.0)

    (_, x0, y0), (_, x1, y1) = api.events
    assert windows_pixel(x0, -1280, 3200) == 0
    assert windows_pixel(x1, -1280, 3200) == 1919
    assert windows_pixel(y1, 0, 1080) == 1079


def test_a_configured_rect_reaches_a_monitor_left_of_the_primary(
    monkeypatch,
) -> None:
    monkeypatch.setenv("BORESIGHT_CURSOR_RECT", "-1280,0,1280,1024")
    api = FakeWin32Api(desktop=Rect(-1280, 0, 3200, 1080))
    backend = Win32CursorBackend(api)

    backend.move_absolute(0.0, 0.0)
    backend.move_absolute(1.0, 0.5)

    (_, x0, _), (_, x1, y1) = api.events
    assert windows_pixel(x0, -1280, 3200) == -1280
    assert windows_pixel(x1, -1280, 3200) == -1
    assert windows_pixel(y1, 0, 1080) == round(0.5 * 1023)


def test_press_move_release_is_a_drag_without_move_on_the_buttons() -> None:
    api = FakeWin32Api()
    backend = Win32CursorBackend(api)

    backend.move_absolute(0.1, 0.1)
    backend.press()
    backend.move_absolute(0.9, 0.9)
    backend.release()

    flags = [flags for flags, _, _ in api.events]
    assert flags == [
        ABSOLUTE_MOVE,
        MOUSEEVENTF_LEFTDOWN,
        ABSOLUTE_MOVE,
        MOUSEEVENTF_LEFTUP,
    ]


def test_a_click_is_down_then_up_and_does_not_move() -> None:
    api = FakeWin32Api()
    backend = Win32CursorBackend(api)

    backend.click()

    assert api.events == [(MOUSEEVENTF_LEFTDOWN, 0, 0), (MOUSEEVENTF_LEFTUP, 0, 0)]


def test_closing_releases_a_held_button_and_only_then() -> None:
    api = FakeWin32Api()
    backend = Win32CursorBackend(api)
    backend.close()
    assert api.events == []

    backend.press()
    backend.close()
    assert api.events[-1] == (MOUSEEVENTF_LEFTUP, 0, 0)


def test_relative_mode_sends_the_delta_before_the_absolute_move() -> None:
    api = FakeWin32Api()
    backend = Win32CursorBackend(api, rel_scale=1000)

    backend.move_absolute(0.5, 0.5)
    backend.move_absolute(0.6, 0.45)

    assert len(api.batches[0]) == 1
    relative, absolute = api.batches[1]
    assert relative == (MOUSEEVENTF_MOVE, 100, -50)
    assert absolute[0] == ABSOLUTE_MOVE


def test_relative_mode_is_off_by_default() -> None:
    api = FakeWin32Api()
    backend = Win32CursorBackend(api)

    backend.move_absolute(0.5, 0.5)
    backend.move_absolute(0.6, 0.6)

    assert all(flags == ABSOLUTE_MOVE for flags, _, _ in api.events)


def test_blocked_input_warns_once(caplog) -> None:
    api = FakeWin32Api(accept=False)
    backend = Win32CursorBackend(api)

    backend.move_absolute(0.5, 0.5)
    backend.click()

    warnings = [r for r in caplog.records if "administrator" in r.getMessage()]
    assert len(warnings) == 1


def test_no_desktop_fails_at_startup() -> None:
    api = FakeWin32Api(primary=Rect(0, 0, 0, 0))
    with pytest.raises(CursorBackendUnavailable, match="no desktop"):
        Win32CursorBackend(api)


@pytest.mark.skipif(sys.platform != "win32", reason="needs user32")
def test_the_real_windows_api_reads_the_desktop() -> None:
    from boresight.inject_win32 import User32Api

    api = User32Api()
    api.make_dpi_aware()
    desktop = api.virtual_screen()
    primary = api.primary_screen()
    assert desktop.width >= primary.width >= 0


# -- macOS -------------------------------------------------------------


class FakeQuartzApi:
    def __init__(
        self,
        allowed: bool = True,
        display: Rect = MAIN_DISPLAY,
        cursor: tuple[float, float] = (10.0, 20.0),
    ) -> None:
        self.allowed = allowed
        self.display = display
        self.cursor = cursor
        self.requested = False
        self.events: list[tuple[int, float, float, dict[int, int]]] = []

    def can_post_events(self) -> bool:
        return self.allowed

    def request_post_events(self) -> None:
        self.requested = True

    def main_display_bounds(self) -> Rect:
        return self.display

    def cursor_location(self) -> tuple[float, float]:
        return self.cursor

    def post_mouse_event(self, event_type, x, y, fields) -> None:
        self.events.append((event_type, x, y, dict(fields)))

    @property
    def types(self) -> list[int]:
        return [event[0] for event in self.events]


def test_quartz_structures_are_pairs_of_doubles() -> None:
    assert ctypes.sizeof(CGPoint) == 16
    assert ctypes.sizeof(CGRect) == 32
    assert CGRect.size.offset == 16


def test_without_permission_startup_fails_and_asks_the_os() -> None:
    api = FakeQuartzApi(allowed=False)
    with pytest.raises(CursorBackendUnavailable) as raised:
        QuartzCursorBackend(api)
    assert str(raised.value) == ACCESSIBILITY_HINT
    assert "Privacy & Security > Accessibility" in ACCESSIBILITY_HINT
    assert "restart" in ACCESSIBILITY_HINT
    assert api.requested
    assert api.events == []


def test_a_mac_move_lands_in_global_points_of_the_main_display() -> None:
    api = FakeQuartzApi()
    backend = QuartzCursorBackend(api)

    backend.move_absolute(0.0, 0.0)
    backend.move_absolute(1.0, 0.5)

    assert api.events == [
        (kCGEventMouseMoved, 0.0, 0.0, {}),
        (kCGEventMouseMoved, 1439.0, 0.5 * 899, {}),
    ]


def test_a_configured_rect_places_a_secondary_display(monkeypatch) -> None:
    monkeypatch.setenv("BORESIGHT_CURSOR_RECT", "-1920,-200,1920,1080")
    api = FakeQuartzApi()
    backend = QuartzCursorBackend(api)

    backend.move_absolute(0.0, 0.0)

    assert api.events[0][1:3] == (-1920.0, -200.0)


def test_a_move_while_held_is_a_drag_and_after_release_is_not() -> None:
    api = FakeQuartzApi()
    backend = QuartzCursorBackend(api)

    backend.move_absolute(0.1, 0.1)
    backend.press()
    backend.move_absolute(0.5, 0.5)
    backend.release()
    backend.move_absolute(0.6, 0.6)

    assert api.types == [
        kCGEventMouseMoved,
        kCGEventLeftMouseDown,
        kCGEventLeftMouseDragged,
        kCGEventLeftMouseUp,
        kCGEventMouseMoved,
    ]
    down, up = api.events[1], api.events[3]
    # Down where the cursor was, up where the drag left it.
    assert down[1:3] == api.events[0][1:3]
    assert up[1:3] == api.events[2][1:3]


def test_a_mac_click_is_down_then_up_with_click_state_one() -> None:
    api = FakeQuartzApi()
    backend = QuartzCursorBackend(api)

    backend.move_absolute(0.5, 0.5)
    backend.click()

    (_, *moved), down, up = api.events
    assert down[0] == kCGEventLeftMouseDown
    assert up[0] == kCGEventLeftMouseUp
    assert down[1:3] == up[1:3] == tuple(moved[:2])
    assert down[3] == up[3] == {kCGMouseEventClickState: 1}


def test_a_press_before_any_move_acts_where_the_cursor_is() -> None:
    api = FakeQuartzApi(cursor=(321.0, 123.0))
    backend = QuartzCursorBackend(api)

    backend.click()

    assert [event[1:3] for event in api.events] == [(321.0, 123.0)] * 2


def test_closing_a_mac_backend_releases_a_held_button() -> None:
    api = FakeQuartzApi()
    backend = QuartzCursorBackend(api)
    backend.close()
    assert api.events == []

    backend.press()
    backend.close()
    assert api.types == [kCGEventLeftMouseDown, kCGEventLeftMouseUp]


def test_mac_relative_mode_carries_the_delta_on_the_move() -> None:
    api = FakeQuartzApi()
    backend = QuartzCursorBackend(api, rel_scale=1000)

    backend.move_absolute(0.5, 0.5)
    backend.move_absolute(0.6, 0.45)

    assert api.events[0][3] == {}
    assert api.events[1][3] == {kCGMouseEventDeltaX: 100, kCGMouseEventDeltaY: -50}


@pytest.mark.skipif(sys.platform != "darwin", reason="needs CoreGraphics")
def test_the_real_quartz_api_reads_the_main_display() -> None:
    from boresight.inject_darwin import CoreGraphicsApi

    api = CoreGraphicsApi()
    api.can_post_events()
    bounds = api.main_display_bounds()
    assert bounds.width >= 0 and bounds.height >= 0
