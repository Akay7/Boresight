"""The USB mouse the gun presents: its report format and its failure modes."""

from __future__ import annotations

import errno

import pytest

from boresight.gun import hid
from boresight.gun.hid import (
    REPORT_DESCRIPTOR,
    REPORT_SIZE,
    DeviceSink,
    HidGadgetBackend,
    pack_report,
    parse_report,
)


class Recorder:
    def __init__(self) -> None:
        self.reports: list[bytes] = []
        self.closed = False

    def write(self, report: bytes) -> None:
        self.reports.append(report)

    def close(self) -> None:
        self.closed = True


def _input_bits(descriptor: bytes) -> tuple[int, int | None]:
    """Total Input bits and the Logical Maximum of the last axis, read from
    the descriptor itself: what a host will expect of every report."""
    bits = 0
    size = count = 0
    maximum = None
    i = 0
    while i < len(descriptor):
        prefix = descriptor[i]
        length = {0: 0, 1: 1, 2: 2, 3: 4}[prefix & 3]
        value = int.from_bytes(descriptor[i + 1 : i + 1 + length], "little")
        tag = prefix & 0xFC
        if tag == 0x74:  # Report Size
            size = value
        elif tag == 0x94:  # Report Count
            count = value
        elif tag == 0x24:  # Logical Maximum
            maximum = value
        elif tag == 0x80:  # Input
            bits += size * count
        i += 1 + length
    return bits, maximum


def test_the_descriptor_declares_the_report_the_backend_sends() -> None:
    bits, maximum = _input_bits(REPORT_DESCRIPTOR)

    assert bits == REPORT_SIZE * 8
    assert maximum == hid.AXIS_MAX
    assert len(pack_report(0.5, 0.5, False)) == REPORT_SIZE


@pytest.mark.parametrize(
    ("x", "y", "raw"),
    [(0.0, 0.0, (0, 0)), (1.0, 1.0, (32767, 32767)), (0.5, 0.25, (16384, 8192))],
)
def test_normalized_aim_maps_to_the_axis_range(x, y, raw) -> None:
    report = pack_report(x, y, False)

    assert (
        int.from_bytes(report[1:3], "little"),
        int.from_bytes(report[3:5], "little"),
    ) == raw
    assert parse_report(report)[2] is False


def test_aim_beyond_the_display_is_clamped() -> None:
    assert pack_report(-3.0, 9.0, False) == pack_report(0.0, 1.0, False)


def test_a_press_does_not_move_the_cursor() -> None:
    sink = Recorder()
    backend = HidGadgetBackend(sink)

    backend.move_absolute(0.25, 0.75)
    backend.press()
    backend.release()

    moved, pressed, released = (parse_report(r) for r in sink.reports)
    assert pressed[:2] == moved[:2] == released[:2]
    assert (moved[2], pressed[2], released[2]) == (False, True, False)


def test_a_click_is_a_press_then_a_release() -> None:
    sink = Recorder()

    HidGadgetBackend(sink).click()

    assert [parse_report(r)[2] for r in sink.reports] == [True, False]


def test_a_held_button_is_released_on_close() -> None:
    sink = Recorder()
    backend = HidGadgetBackend(sink)
    backend.press()

    backend.close()

    assert parse_report(sink.reports[-1])[2] is False
    assert sink.closed


def test_close_with_nothing_held_sends_nothing() -> None:
    sink = Recorder()

    HidGadgetBackend(sink).close()

    assert sink.reports == []


def test_a_report_after_a_drop_carries_the_whole_state() -> None:
    """A press dropped by a suspended host is repaired by the next move."""
    sink = Recorder()
    backend = HidGadgetBackend(sink)
    backend.press()
    sink.reports.clear()  # the host never saw it

    backend.move_absolute(0.1, 0.2)

    assert parse_report(sink.reports[0])[2] is True


class FakeOS:
    """os.open/os.write with a host that can go away and come back."""

    def __init__(self) -> None:
        self.opened = 0
        self.written: list[bytes] = []
        self.fail: OSError | None = None

    def open(self, path, flags):
        self.opened += 1
        return 100 + self.opened

    def write(self, fd, data):
        if self.fail is not None:
            raise self.fail
        self.written.append(data)
        return len(data)

    def close(self, fd):
        pass


@pytest.fixture
def fake_os(monkeypatch) -> FakeOS:
    fake = FakeOS()
    monkeypatch.setattr(hid.os, "open", fake.open)
    monkeypatch.setattr(hid.os, "write", fake.write)
    monkeypatch.setattr(hid.os, "close", fake.close)
    return fake


def test_a_host_that_is_not_reading_drops_without_raising(fake_os) -> None:
    sink = DeviceSink("/dev/hidg0")
    fake_os.fail = BlockingIOError(errno.EAGAIN, "again")

    sink.write(b"12345")
    sink.write(b"12345")

    assert sink.dropped == 2
    assert fake_os.opened == 1  # a slow host does not cause reopening


def test_the_device_is_reopened_after_the_host_goes_away(fake_os) -> None:
    sink = DeviceSink("/dev/hidg0")
    sink.write(b"12345")
    fake_os.fail = OSError(errno.ESHUTDOWN, "cable out")
    sink.write(b"12345")
    fake_os.fail = None

    sink.write(b"67890")

    assert fake_os.opened == 2
    assert fake_os.written == [b"12345", b"67890"]


def test_an_unopenable_device_drops_and_retries(fake_os, monkeypatch) -> None:
    def refuse(path, flags):
        raise OSError(errno.ENOENT, "no such device")

    monkeypatch.setattr(hid.os, "open", refuse)
    sink = DeviceSink("/dev/hidg0")

    sink.write(b"12345")

    assert sink.dropped == 1
    monkeypatch.setattr(hid.os, "open", fake_os.open)
    sink.write(b"12345")
    assert fake_os.written == [b"12345"]
