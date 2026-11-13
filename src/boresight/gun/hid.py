"""The USB mouse the gun presents, and the cursor backend that drives it.

One report descriptor, declared once, is what both the gadget setup script
(`deploy/pi/`) and the tests read. The device is an absolute mouse, not a
digitizer: some hosts treat a digitizer as touch and hide the pointer.
Axes run 0..32767, so a normalized aim maps to them without the Pi ever
knowing the host's resolution.
"""

from __future__ import annotations

import errno
import logging
import os
import struct
import threading
from typing import Protocol

logger = logging.getLogger(__name__)

AXIS_MAX = 32767

# Mouse, one button (padded to a byte), then X and Y as 16-bit absolute.
# fmt: off
REPORT_DESCRIPTOR = bytes([
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x02,        # Usage (Mouse)
    0xA1, 0x01,        # Collection (Application)
    0x09, 0x01,        #   Usage (Pointer)
    0xA1, 0x00,        #   Collection (Physical)
    0x05, 0x09,        #     Usage Page (Button)
    0x19, 0x01,        #     Usage Minimum (1)
    0x29, 0x01,        #     Usage Maximum (1)
    0x15, 0x00,        #     Logical Minimum (0)
    0x25, 0x01,        #     Logical Maximum (1)
    0x95, 0x01,        #     Report Count (1)
    0x75, 0x01,        #     Report Size (1)
    0x81, 0x02,        #     Input (Data, Variable, Absolute)
    0x95, 0x01,        #     Report Count (1)
    0x75, 0x07,        #     Report Size (7)
    0x81, 0x03,        #     Input (Constant): padding
    0x05, 0x01,        #     Usage Page (Generic Desktop)
    0x09, 0x30,        #     Usage (X)
    0x09, 0x31,        #     Usage (Y)
    0x15, 0x00,        #     Logical Minimum (0)
    0x26, 0xFF, 0x7F,  #     Logical Maximum (32767)
    0x75, 0x10,        #     Report Size (16)
    0x95, 0x02,        #     Report Count (2)
    0x81, 0x02,        #     Input (Data, Variable, Absolute)
    0xC0,              #   End Collection
    0xC0,              # End Collection
])
# fmt: on

REPORT_SIZE = 5
_REPORT = struct.Struct("<BHH")

# A report that cannot go out because the host is gone or not listening.
_HOST_GONE = {errno.ESHUTDOWN, errno.ENODEV, errno.EPIPE, errno.EIO, errno.ENOTCONN}


def pack_report(x: float, y: float, pressed: bool) -> bytes:
    """A report for normalized `x`, `y`, clamped into the display."""
    return _REPORT.pack(1 if pressed else 0, _axis(x), _axis(y))


def parse_report(report: bytes) -> tuple[float, float, bool]:
    """The inverse of `pack_report`: normalized x, y and the button."""
    if len(report) != REPORT_SIZE:
        raise ValueError(f"a report is {REPORT_SIZE} bytes, got {len(report)}")
    buttons, x, y = _REPORT.unpack(report)
    return x / AXIS_MAX, y / AXIS_MAX, bool(buttons & 1)


def _axis(value: float) -> int:
    return round(min(1.0, max(0.0, value)) * AXIS_MAX)


class ReportSink(Protocol):
    def write(self, report: bytes) -> None: ...
    def close(self) -> None: ...


class DeviceSink:
    """`/dev/hidg0`, written without ever blocking the aim loop.

    A host that is suspended, unplugged or not yet enumerated makes the
    write fail rather than wait. That drops the report: the next one
    carries the whole state, so nothing stays wrong. After the host goes
    away the descriptor is closed and reopened by the next write, which is
    how a replugged cable works without restarting anything.
    """

    def __init__(self, path: str = "/dev/hidg0") -> None:
        self._path = path
        self._fd: int | None = None
        self.dropped = 0
        self._warned = False

    def write(self, report: bytes) -> None:
        try:
            if self._fd is None:
                self._fd = os.open(self._path, os.O_WRONLY | os.O_NONBLOCK)
            os.write(self._fd, report)
            self._warned = False
        except BlockingIOError:
            self._drop("host is not reading reports")
        except OSError as error:
            if error.errno in _HOST_GONE or self._fd is None:
                self._reopen_next_time()
            self._drop(f"{error.strerror or error}")

    def _reopen_next_time(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
        self._fd = None

    def _drop(self, why: str) -> None:
        self.dropped += 1
        if not self._warned:
            # Once per outage; a host that is gone is not an error.
            logger.warning("dropping HID reports to %s: %s", self._path, why)
            self._warned = True

    def close(self) -> None:
        self._reopen_next_time()


class HidGadgetBackend:
    """A `CursorBackend` that reports to the host as a USB mouse.

    Every report carries the full state, the last position and the button,
    so a press never moves the cursor and a dropped report is repaired by
    the next. Called from the aim thread and the trigger thread.
    """

    def __init__(self, sink: ReportSink) -> None:
        self._sink = sink
        self._lock = threading.Lock()
        self._x = 0.5
        self._y = 0.5
        self._pressed = False

    def move_absolute(self, x: float, y: float) -> None:
        with self._lock:
            self._x, self._y = x, y
            self._send()

    def press(self) -> None:
        with self._lock:
            self._pressed = True
            self._send()

    def release(self) -> None:
        with self._lock:
            self._pressed = False
            self._send()

    def click(self) -> None:
        self.press()
        self.release()

    def close(self) -> None:
        """Lets go of a held button before the device goes away."""
        with self._lock:
            if self._pressed:
                self._pressed = False
                self._send()
        self._sink.close()

    def _send(self) -> None:
        self._sink.write(pack_report(self._x, self._y, self._pressed))
