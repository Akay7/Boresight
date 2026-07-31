"""Unit tests for the frame codec, the drop slot, and the counters.

No server, no sockets, no images. The pieces here are deliberately
independent of FastAPI so the transport's two load-bearing behaviours --
that a malformed message costs one frame rather than a session, and that
a backlog collapses to its newest member -- can be asserted directly
instead of raced against a real connection.
"""

from __future__ import annotations

import asyncio

import pytest

from boresight.stream import (
    HEADER_SIZE,
    FrameDecodeError,
    FrameSlot,
    SessionStats,
    pack_frame,
    unpack_frame,
)

# --- Codec -----------------------------------------------------------


def test_a_frame_round_trips() -> None:
    message = pack_frame(1234.5, b"\xff\xd8jpeg-ish\xff\xd9")

    client_ms, payload = unpack_frame(message)

    assert client_ms == 1234.5
    assert payload == b"\xff\xd8jpeg-ish\xff\xd9"


def test_the_header_is_eight_bytes() -> None:
    """Pinned because the client writes it from JavaScript, where the
    size is spelled out separately and cannot be imported from here."""
    assert HEADER_SIZE == 8
    assert len(pack_frame(0.0, b"")) == 8


@pytest.mark.parametrize("length", [0, 1, HEADER_SIZE - 1])
def test_a_message_shorter_than_the_header_is_rejected(length: int) -> None:
    with pytest.raises(FrameDecodeError, match="shorter than"):
        unpack_frame(b"\x00" * length)


def test_a_header_with_no_image_is_rejected() -> None:
    with pytest.raises(FrameDecodeError, match="no image data"):
        unpack_frame(pack_frame(1.0, b""))


def test_the_payload_is_not_validated_as_an_image() -> None:
    """Decoding is the image decoder's job. Both failures are counted
    the same way, so splitting the responsibility buys nothing."""
    _client_ms, payload = unpack_frame(pack_frame(1.0, b"not a jpeg"))

    assert payload == b"not a jpeg"


# --- Drop slot -------------------------------------------------------


def test_a_single_frame_is_returned() -> None:
    async def run() -> tuple[float, bytes]:
        slot = FrameSlot()
        slot.put(1.0, b"a")
        return await slot.get()

    assert asyncio.run(run()) == (1.0, b"a")


def test_a_backlog_collapses_to_the_newest_frame() -> None:
    """The whole point of the slot. Four frames arrive while nothing is
    consuming; the consumer gets the last one and the other three are
    counted as dropped, not queued behind it."""

    async def run() -> tuple[tuple[float, bytes], int]:
        slot = FrameSlot()
        for index, payload in enumerate([b"a", b"b", b"c", b"d"]):
            slot.put(float(index), payload)
        return await slot.get(), slot.dropped

    (item, dropped) = asyncio.run(run())

    assert item == (3.0, b"d")
    assert dropped == 3


def test_taking_a_frame_clears_the_slot() -> None:
    """After a get, the next put is not a drop -- nothing was waiting."""

    async def run() -> int:
        slot = FrameSlot()
        slot.put(1.0, b"a")
        await slot.get()
        slot.put(2.0, b"b")
        return slot.dropped

    assert asyncio.run(run()) == 0


def test_get_waits_for_a_frame_rather_than_returning_stale_data() -> None:
    async def run() -> tuple[float, bytes]:
        slot = FrameSlot()

        async def put_later() -> None:
            await asyncio.sleep(0.01)
            slot.put(9.0, b"late")

        task = asyncio.create_task(put_later())
        item = await asyncio.wait_for(slot.get(), timeout=1.0)
        await task
        return item

    assert asyncio.run(run()) == (9.0, b"late")


def test_pending_reports_whether_a_frame_is_waiting() -> None:
    async def run() -> tuple[bool, bool, bool]:
        slot = FrameSlot()
        empty = slot.pending
        slot.put(1.0, b"a")
        filled = slot.pending
        await slot.get()
        return empty, filled, slot.pending

    assert asyncio.run(run()) == (False, True, False)


# --- Counters --------------------------------------------------------


def test_stats_start_at_zero() -> None:
    stats = SessionStats()

    assert (stats.received, stats.processed, stats.dropped, stats.failed) == (0,) * 4


def test_dropped_is_read_from_the_slot() -> None:
    """Dropping happens in the slot, so the count lives there. Copying it
    into the stats would create a second source of truth that can drift."""
    slot = FrameSlot()
    stats = SessionStats(_slot=slot)
    slot.put(1.0, b"a")
    slot.put(2.0, b"b")

    assert stats.dropped == 1


def test_counts_reconcile_against_received() -> None:
    slot = FrameSlot()
    stats = SessionStats(_slot=slot, received=10, processed=6, failed=2)
    slot.put(1.0, b"a")
    slot.put(2.0, b"b")

    assert stats.dropped == 1
    assert stats.reconciles()


def test_double_counting_a_frame_fails_reconciliation() -> None:
    """The assertion has to be able to fail, or it asserts nothing."""
    stats = SessionStats(received=3, processed=3, failed=1)

    assert not stats.reconciles()


def test_the_telemetry_message_carries_the_counts() -> None:
    slot = FrameSlot()
    stats = SessionStats(_slot=slot, received=5, processed=4, failed=0)
    slot.put(1.0, b"a")
    slot.put(2.0, b"b")

    message = stats.as_message()

    assert message["type"] == "stats"
    assert message["received"] == 5
    assert message["processed"] == 4
    assert message["dropped"] == 1
