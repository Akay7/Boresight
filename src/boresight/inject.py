"""Cursor injection backends.

Coordinates are normalized floats in [0.0, 1.0] (fraction of screen
width/height). The uinput backend maps them onto the device's absolute
axis range, 0-32767, matching the 16-bit HID absolute range Boresight's
future hardware paths also target.
"""

from __future__ import annotations

from typing import Protocol

ABS_MAX = 32767


class CursorBackend(Protocol):
    def move_absolute(self, x: float, y: float) -> None: ...


class CursorBackendUnavailable(RuntimeError):
    """Raised when a cursor backend cannot be initialized (e.g. no
    permission to open /dev/uinput, or the uinput kernel module is
    unavailable)."""


class UinputCursorBackend:
    """Moves the cursor via a virtual absolute pointer on Linux uinput."""

    def __init__(self) -> None:
        try:
            from evdev import AbsInfo, UInput, ecodes
        except ImportError as exc:  # pragma: no cover - platform guard
            raise CursorBackendUnavailable(
                "evdev is not available (uinput backend requires Linux)"
            ) from exc

        abs_info = AbsInfo(value=0, min=0, max=ABS_MAX, fuzz=0, flat=0, resolution=0)
        capabilities = {
            ecodes.EV_ABS: [
                (ecodes.ABS_X, abs_info),
                (ecodes.ABS_Y, abs_info),
            ],
            # A pure-EV_ABS device with no buttons is classified as a
            # joystick by the kernel/libinput and ignored for pointer
            # positioning (verified against a running X11 session —
            # without any EV_KEY capability the writes are silently
            # dropped). ABS_X/ABS_Y + BTN_TOUCH + INPUT_PROP_DIRECT is
            # the standard single-touch-touchscreen evdev signature:
            # udev's input_id tags it ID_INPUT_TOUCHSCREEN=1 and
            # libinput places the (core) pointer directly at the
            # reported coordinate. BTN_LEFT alone (no BTN_TOUCH) gets
            # tagged ID_INPUT_MOUSE=1 and run through relative-motion
            # acceleration instead; adding BTN_TOOL_PEN/BTN_STYLUS gets
            # tagged ID_INPUT_TABLET=1, which libinput's tablet backend
            # then rejects for lacking real stylus/pressure capabilities.
            # Both were verified against a running X11 session.
            ecodes.EV_KEY: [ecodes.BTN_TOUCH],
        }
        try:
            # INPUT_PROP_DIRECT tells libinput this is an absolute
            # pointer (like a graphics tablet), not a relative mouse.
            # Without it libinput classifies an ABS+BTN_LEFT device as
            # type MOUSE and runs its events through pointer
            # acceleration/relative-delta translation instead of
            # placing the cursor directly at the reported coordinates.
            self._device = UInput(
                capabilities,
                name="boresight-cursor",
                input_props=[ecodes.INPUT_PROP_DIRECT],
            )
        except OSError as exc:
            raise CursorBackendUnavailable(
                "Could not open /dev/uinput. Check that the uinput kernel "
                "module is loaded and this process has read/write access "
                "to the device (see the change's setup notes for the "
                "udev rule)."
            ) from exc

        self._ecodes = ecodes

    def move_absolute(self, x: float, y: float) -> None:
        abs_x = round(x * ABS_MAX)
        abs_y = round(y * ABS_MAX)
        # BTN_TOUCH down -> position -> up: the touchscreen device type
        # only updates the (visible) core pointer position while a touch
        # is active. A press-move-release per call is the equivalent of
        # a synthetic tap at the target position.
        self._device.write(self._ecodes.EV_KEY, self._ecodes.BTN_TOUCH, 1)
        self._device.write(self._ecodes.EV_ABS, self._ecodes.ABS_X, abs_x)
        self._device.write(self._ecodes.EV_ABS, self._ecodes.ABS_Y, abs_y)
        self._device.syn()
        self._device.write(self._ecodes.EV_KEY, self._ecodes.BTN_TOUCH, 0)
        self._device.syn()

    def close(self) -> None:
        self._device.close()


class FakeCursorBackend:
    """Records calls instead of touching a real device. Test-only."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, float]] = []

    def move_absolute(self, x: float, y: float) -> None:
        self.calls.append((x, y))
