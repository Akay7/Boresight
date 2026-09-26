"""Cursor injection on Windows, over `SendInput`.

Everything that touches the OS is in `Win32Api`, which the backend is
handed; the backend itself only decides which `INPUT` records to send.
That split is what lets the event construction -- structure layout,
coordinate normalisation, button sequences -- be tested on Linux with a
recording fake, since nothing here can run against a real Windows
desktop in this project's CI.

Plain ctypes, not pywin32: the backend needs four functions, and the
core install deliberately stays free of heavy dependencies.
"""

from __future__ import annotations

import ctypes
import logging
from collections.abc import Sequence
from typing import Protocol

from boresight.inject import (
    DEFAULT_REL_SCALE,
    CursorBackendUnavailable,
    Rect,
    cursor_rect_override,
)

log = logging.getLogger(__name__)

INPUT_MOUSE = 0

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

# Absolute coordinates are 0..65535 across the (virtual) desktop.
ABSOLUTE_MAX = 65535

SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2, a pseudo-handle.
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
PROCESS_PER_MONITOR_DPI_AWARE = 2


# Explicit widths rather than ctypes.wintypes: its LONG and DWORD are
# c_long, which is 8 bytes on 64-bit Linux and macOS. Spelled out, the
# structure has the Windows layout on every host, so its size can be
# checked where the tests run. ULONG_PTR is pointer-sized, as c_size_t.
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_int32),
        ("dy", ctypes.c_int32),
        ("mouseData", ctypes.c_uint32),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    # Never sent. Present so the union has its real size whatever the
    # largest member turns out to be on a given pointer width.
    _fields_ = [
        ("wVk", ctypes.c_uint16),
        ("wScan", ctypes.c_uint16),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_uint32), ("u", _INPUTUNION)]


def mouse_input(flags: int, dx: int = 0, dy: int = 0) -> INPUT:
    return INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(dx=dx, dy=dy, dwFlags=flags))


def to_absolute(pixel: int, origin: int, size: int) -> int:
    """A virtual-desktop pixel as a 0..65535 absolute coordinate.

    Windows turns an absolute coordinate back into a pixel as
    `n * size // 65536`, truncating. The ceiling here is the inverse
    that lands on exactly `pixel` every time; the more common
    `pixel * 65535 // (size - 1)` is off by one on a scattering of
    pixels, depending on the width.
    """
    offset = min(max(pixel - origin, 0), size - 1)
    return min(-(-offset * 65536 // size), ABSOLUTE_MAX)


class Win32Api(Protocol):
    def make_dpi_aware(self) -> None: ...
    def primary_screen(self) -> Rect: ...
    def virtual_screen(self) -> Rect: ...
    def send_input(self, inputs: Sequence[INPUT]) -> int: ...


class User32Api:
    """The real `Win32Api`, over user32 (and shcore for DPI)."""

    def __init__(self) -> None:
        try:
            self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        except (AttributeError, OSError) as exc:
            raise CursorBackendUnavailable(
                "user32.dll is not available (the SendInput backend requires Windows)"
            ) from exc
        self._user32.SendInput.argtypes = [
            ctypes.c_uint,
            ctypes.POINTER(INPUT),
            ctypes.c_int,
        ]
        self._user32.SendInput.restype = ctypes.c_uint
        self._user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        self._user32.GetSystemMetrics.restype = ctypes.c_int

    def make_dpi_aware(self) -> None:
        # Without this a scaled display (150% and so on) reports its
        # metrics in scaled pixels, and the target rectangle is wrong
        # by the scale factor. Newest API first; each is absent on some
        # Windows version, and each fails harmlessly if awareness was
        # already set (by the manifest, or by Qt in the same process).
        setter = getattr(self._user32, "SetProcessDpiAwarenessContext", None)
        if setter is not None:
            setter.argtypes = [ctypes.c_void_p]
            setter.restype = ctypes.c_int
            if setter(ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)):
                return
        try:
            shcore = ctypes.WinDLL("shcore")
            if shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE) == 0:
                return
        except (AttributeError, OSError):
            pass
        legacy = getattr(self._user32, "SetProcessDPIAware", None)
        if legacy is not None:
            legacy()

    def _metric(self, index: int) -> int:
        return self._user32.GetSystemMetrics(index)

    def primary_screen(self) -> Rect:
        # The primary monitor's top-left is the virtual desktop's
        # origin by definition.
        return Rect(0, 0, self._metric(SM_CXSCREEN), self._metric(SM_CYSCREEN))

    def virtual_screen(self) -> Rect:
        return Rect(
            self._metric(SM_XVIRTUALSCREEN),
            self._metric(SM_YVIRTUALSCREEN),
            self._metric(SM_CXVIRTUALSCREEN),
            self._metric(SM_CYVIRTUALSCREEN),
        )

    def send_input(self, inputs: Sequence[INPUT]) -> int:
        array = (INPUT * len(inputs))(*inputs)
        return self._user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))


class Win32CursorBackend:
    """Moves the cursor and presses the left button with `SendInput`."""

    def __init__(
        self,
        api: Win32Api | None = None,
        target: Rect | None = None,
        rel_scale: float = DEFAULT_REL_SCALE,
    ) -> None:
        self._api = api if api is not None else User32Api()
        # Before any metric is read: see `User32Api.make_dpi_aware`.
        self._api.make_dpi_aware()
        self._desktop = self._api.virtual_screen()
        if self._desktop.width < 1 or self._desktop.height < 1:
            # A service or a disconnected session has no desktop to
            # place a cursor on.
            raise CursorBackendUnavailable(
                "Windows reports no desktop to move the cursor on. Run "
                "the server in the logged-in user's session."
            )
        if target is None:
            target = cursor_rect_override()
        self._target = target if target is not None else self._api.primary_screen()
        self._rel_scale = rel_scale
        self._last_position: tuple[float, float] | None = None
        self._held = False
        self._warned_blocked = False

    def _absolute(self, x: float, y: float) -> tuple[int, int]:
        px, py = self._target.point(x, y)
        desktop = self._desktop
        return (
            to_absolute(round(px), int(desktop.x), int(desktop.width)),
            to_absolute(round(py), int(desktop.y), int(desktop.height)),
        )

    def _send(self, *inputs: INPUT) -> None:
        sent = self._api.send_input(inputs)
        if sent != len(inputs) and not self._warned_blocked:
            # Not raised: UIPI drops injected input aimed at a window
            # running elevated, and that ends when focus moves on.
            # Ending the session over it would be worse.
            self._warned_blocked = True
            log.warning(
                "SendInput delivered %d of %d events. Windows blocks "
                "injected input to a window running as administrator "
                "unless Boresight runs elevated too.",
                sent,
                len(inputs),
            )

    @property
    def rel_scale(self) -> float:
        return self._rel_scale

    @rel_scale.setter
    def rel_scale(self, value: float) -> None:
        # A live setting, as on `UInputCursorBackend.rel_scale`.
        self._rel_scale = value

    def move_absolute(self, x: float, y: float) -> None:
        inputs = []
        # Relative first, for a title reading raw mouse motion (see
        # `DEFAULT_REL_SCALE` in inject.py before enabling it). The
        # absolute placement after it then puts the OS cursor exactly
        # on target, whatever acceleration did to the delta.
        if self._last_position is not None and self._rel_scale:
            last_x, last_y = self._last_position
            rel_x = round((x - last_x) * self._rel_scale)
            rel_y = round((y - last_y) * self._rel_scale)
            if rel_x or rel_y:
                inputs.append(mouse_input(MOUSEEVENTF_MOVE, rel_x, rel_y))
        abs_x, abs_y = self._absolute(x, y)
        inputs.append(
            mouse_input(
                MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                abs_x,
                abs_y,
            )
        )
        self._send(*inputs)
        self._last_position = (x, y)

    def click(self) -> None:
        self.press()
        self.release()

    def press(self) -> None:
        # No MOVE flag: the button goes down wherever the cursor is.
        self._send(mouse_input(MOUSEEVENTF_LEFTDOWN))
        self._held = True

    def release(self) -> None:
        self._send(mouse_input(MOUSEEVENTF_LEFTUP))
        self._held = False

    def close(self) -> None:
        if self._held:
            self.release()
