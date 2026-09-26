"""`UinputCursorBackend`'s relative-delta emission, against a fake device.

A real `/dev/uinput` is root-owned and not available in most dev/CI
environments (the rest of the suite tests this backend's *policy* --
smoothing, holding, click semantics -- entirely through
`FakeCursorBackend`, never the real one). Faking `evdev.UInput` itself
here lets the actual delta arithmetic in `UinputCursorBackend` run
end-to-end without needing real hardware access, the same way the rest
of the suite avoids a real display for the Qt overlay.
"""

from __future__ import annotations

import pytest

evdev = pytest.importorskip("evdev", reason="uinput backend requires evdev (Linux)")

from boresight.inject import UinputCursorBackend  # noqa: E402


class FakeUInput:
    """Records writes instead of touching a real device."""

    instances: list[FakeUInput] = []

    def __init__(self, capabilities=None, name="", input_props=None, product=None):
        self.name = name
        self.capabilities = capabilities or {}
        self.product = product
        self.events: list[tuple[int, int, int]] = []
        self.closed = False
        FakeUInput.instances.append(self)

    def write(self, etype: int, code: int, value: int) -> None:
        self.events.append((etype, code, value))

    def syn(self) -> None:
        self.events.append(("SYN",))

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def fake_uinput(monkeypatch):
    FakeUInput.instances = []
    monkeypatch.setattr(evdev, "UInput", FakeUInput)
    yield FakeUInput.instances


def _writes(fake: FakeUInput) -> list[tuple[int, int, int]]:
    """Just the `write()` calls, filtering out `syn()`'s bare marker."""
    return [event for event in fake.events if len(event) == 3]


def _relative_events(fake: FakeUInput, code) -> list[int]:
    return [
        value
        for etype, c, value in _writes(fake)
        if etype == evdev.ecodes.EV_REL and c == code
    ]


def test_two_uinput_devices_are_created(fake_uinput) -> None:
    UinputCursorBackend()

    assert len(fake_uinput) == 2
    assert fake_uinput[0].name == "boresight-cursor"
    assert fake_uinput[1].name == "boresight-trigger"


def test_the_first_move_emits_no_relative_delta(fake_uinput) -> None:
    """No prior position to take a delta against yet -- emitting one
    would be a spurious jump from an arbitrary starting point."""
    backend = UinputCursorBackend()

    backend.move_absolute(0.5, 0.5)

    relative_device = fake_uinput[1]
    assert _relative_events(relative_device, evdev.ecodes.REL_X) == []
    assert _relative_events(relative_device, evdev.ecodes.REL_Y) == []


def test_a_second_move_emits_a_delta_from_the_first(fake_uinput) -> None:
    backend = UinputCursorBackend(rel_scale=1000)

    backend.move_absolute(0.5, 0.5)
    backend.move_absolute(0.6, 0.45)

    relative_device = fake_uinput[1]
    assert _relative_events(relative_device, evdev.ecodes.REL_X) == [100]
    assert _relative_events(relative_device, evdev.ecodes.REL_Y) == [-50]


def test_a_zero_delta_emits_no_relative_event(fake_uinput) -> None:
    backend = UinputCursorBackend()

    backend.move_absolute(0.5, 0.5)
    backend.move_absolute(0.5, 0.5)

    relative_device = fake_uinput[1]
    assert _relative_events(relative_device, evdev.ecodes.REL_X) == []
    assert _relative_events(relative_device, evdev.ecodes.REL_Y) == []


def test_every_move_still_emits_the_absolute_placement(fake_uinput) -> None:
    """The relative delta is additional, not a replacement -- a title
    reading the OS cursor position must see every move exactly as
    before this change."""
    backend = UinputCursorBackend(rel_scale=1000)

    backend.move_absolute(0.5, 0.5)
    backend.move_absolute(0.6, 0.45)

    cursor_device = fake_uinput[0]
    abs_x = [
        value for etype, c, value in _writes(cursor_device) if c == evdev.ecodes.ABS_X
    ]
    abs_y = [
        value for etype, c, value in _writes(cursor_device) if c == evdev.ecodes.ABS_Y
    ]
    assert abs_x[-2:] == [round(0.5 * 32767), round(0.6 * 32767)]
    assert abs_y[-2:] == [round(0.5 * 32767), round(0.45 * 32767)]


def test_rel_scale_controls_the_delta_magnitude(fake_uinput) -> None:
    backend = UinputCursorBackend(rel_scale=2000)

    backend.move_absolute(0.5, 0.5)
    backend.move_absolute(0.6, 0.5)

    relative_device = fake_uinput[1]
    assert _relative_events(relative_device, evdev.ecodes.REL_X) == [200]


def test_rel_scale_can_change_between_moves(fake_uinput) -> None:
    """A live setting: the next move uses the new scale, and the delta
    is still taken from the last position, not reset."""
    backend = UinputCursorBackend()

    backend.move_absolute(0.5, 0.5)
    backend.move_absolute(0.6, 0.5)
    backend.rel_scale = 1000
    backend.move_absolute(0.7, 0.5)

    relative_device = fake_uinput[1]
    assert backend.rel_scale == 1000
    assert _relative_events(relative_device, evdev.ecodes.REL_X) == [100]


def test_relative_deltas_are_off_by_default(fake_uinput) -> None:
    """The random-walk drift risk described in inject.py's module
    docstring means this must be opt-in, not merely conservative by
    default."""
    backend = UinputCursorBackend()

    backend.move_absolute(0.5, 0.5)
    backend.move_absolute(0.9, 0.9)

    relative_device = fake_uinput[1]
    assert _relative_events(relative_device, evdev.ecodes.REL_X) == []
    assert _relative_events(relative_device, evdev.ecodes.REL_Y) == []


def test_click_is_a_pen_tap_not_a_mouse_button(fake_uinput) -> None:
    """Tip down then up on the pen, so the click lands where the pen
    hovers -- a mouse button on the other device would land at a
    separate Wayland pointer's position instead."""
    backend = UinputCursorBackend()
    pen, relative_device = fake_uinput
    pen.events.clear()

    backend.click()

    assert _writes(relative_device) == []
    touches = [
        value
        for etype, c, value in _writes(pen)
        if etype == evdev.ecodes.EV_KEY and c == evdev.ecodes.BTN_TOUCH
    ]
    pressures = [
        value
        for etype, c, value in _writes(pen)
        if etype == evdev.ecodes.EV_ABS and c == evdev.ecodes.ABS_PRESSURE
    ]
    assert touches == [1, 0]
    assert pressures[0] > 0 and pressures[-1] == 0
    # Down and up are separate frames, or they cancel out.
    assert pen.events.count(("SYN",)) == 2


def _tip(fake: FakeUInput) -> list[tuple[int, int]]:
    """Tip and position writes, in order, as (code, value)."""
    codes = {
        evdev.ecodes.BTN_TOUCH,
        evdev.ecodes.ABS_X,
    }
    return [(c, value) for _, c, value in _writes(fake) if c in codes]


def test_press_move_release_is_a_drag(fake_uinput) -> None:
    backend = UinputCursorBackend()
    pen = fake_uinput[0]
    pen.events.clear()

    backend.press()
    backend.move_absolute(1.0, 0.0)
    backend.release()

    touch, abs_x = evdev.ecodes.BTN_TOUCH, evdev.ecodes.ABS_X
    # Down, moved with it down, then up: not a tap followed by a move.
    assert _tip(pen) == [(touch, 1), (abs_x, 32767), (touch, 0)]


def test_close_lifts_a_held_tip(fake_uinput) -> None:
    backend = UinputCursorBackend()
    pen = fake_uinput[0]
    backend.press()
    pen.events.clear()

    backend.close()

    touches = [
        value
        for etype, c, value in _writes(pen)
        if etype == evdev.ecodes.EV_KEY and c == evdev.ecodes.BTN_TOUCH
    ]
    assert touches == [0]


def test_close_without_a_hold_does_not_touch_the_tip(fake_uinput) -> None:
    backend = UinputCursorBackend()
    pen = fake_uinput[0]
    pen.events.clear()

    backend.close()

    assert all(c != evdev.ecodes.BTN_TOUCH for _, c, _ in _writes(pen))


def test_close_closes_both_devices(fake_uinput) -> None:
    backend = UinputCursorBackend()

    backend.close()

    assert fake_uinput[0].closed
    assert fake_uinput[1].closed
