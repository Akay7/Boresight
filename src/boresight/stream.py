"""The transport layer between the phone's camera and the pipeline.

Three pieces, all independent of FastAPI so they can be tested without
a server: the frame message codec, a single-slot mailbox that drops
stale frames, and the per-connection counters.

The wire format is one frame per binary WebSocket message -- an 8-byte
little-endian timestamp taken by the client at capture, followed by the
frame as JPEG. JPEG because that is already what the checked-in
fixtures are, which makes a fixture file a wire message with an 8-byte
prefix. Text messages on the same socket carry JSON control and
telemetry, leaving room for the trigger event without a second
connection.
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass, field

# One float64, little-endian: milliseconds from the client's own clock.
# Only ever compared against a later reading of that same clock, so the
# two ends never need to agree on an epoch.
_TIMESTAMP = struct.Struct("<d")
HEADER_SIZE = _TIMESTAMP.size


class FrameDecodeError(ValueError):
    """Raised for a message that is not a well-formed frame.

    Deliberately not fatal to a connection. One corrupt frame on a
    lossy Wi-Fi link should cost one frame, not the session.
    """


def pack_frame(client_ms: float, jpeg: bytes) -> bytes:
    """Build one binary frame message."""
    return _TIMESTAMP.pack(client_ms) + jpeg


def unpack_frame(message: bytes) -> tuple[float, bytes]:
    """Split a binary frame message into its timestamp and JPEG bytes.

    Does not validate the JPEG -- that is the decoder's job, and a
    frame that fails there is counted the same way as one that fails
    here.
    """
    if len(message) < HEADER_SIZE:
        raise FrameDecodeError(
            f"frame message is {len(message)} bytes, shorter than the "
            f"{HEADER_SIZE}-byte timestamp header"
        )
    (client_ms,) = _TIMESTAMP.unpack_from(message, 0)
    payload = message[HEADER_SIZE:]
    if not payload:
        raise FrameDecodeError("frame message carries a header but no image data")
    return client_ms, payload


class FrameSlot:
    """Holds exactly one pending frame. Newest wins.

    A queue would convert a throughput shortfall into unbounded,
    monotonically growing latency: ten seconds into a session the
    cursor follows where the player aimed a second ago, and it never
    catches up. Overwriting costs nothing, because the frame being
    discarded is strictly worse information than the one replacing it.
    """

    def __init__(self) -> None:
        self._item: tuple[float, bytes] | None = None
        self._ready = asyncio.Event()
        self.dropped = 0

    def put(self, client_ms: float, payload: bytes) -> None:
        if self._item is not None:
            # Something was still waiting. It is now stale.
            self.dropped += 1
        self._item = (client_ms, payload)
        self._ready.set()

    async def get(self) -> tuple[float, bytes]:
        """Wait for the newest frame and take it."""
        await self._ready.wait()
        assert self._item is not None
        item = self._item
        self._item = None
        self._ready.clear()
        return item

    @property
    def pending(self) -> bool:
        return self._item is not None


@dataclass
class SessionStats:
    """Counters for one connection. A new connection starts at zero."""

    received: int = 0
    processed: int = 0
    failed: int = 0

    decode_ms: float = 0.0
    solve_ms: float = 0.0
    round_trip_ms: float = 0.0

    markers_detected: int = 0
    inside_hull: bool | None = None
    outcome: str | None = None
    position: tuple[float, float] | None = None

    # Owned by the slot, which is where dropping actually happens.
    _slot: FrameSlot | None = field(default=None, repr=False)

    @property
    def dropped(self) -> int:
        return 0 if self._slot is None else self._slot.dropped

    def reconciles(self) -> bool:
        """Every received frame is processed, dropped, failed, or in flight.

        Frames can be in the slot or mid-process when this is read, so
        the accounted total can trail `received` -- but it must never
        exceed it, which would mean a frame was counted twice.
        """
        return self.processed + self.dropped + self.failed <= self.received

    def as_message(self, client_ms: float | None = None) -> dict:
        """The telemetry payload sent back to the phone.

        `client_ms` is the timestamp the phone stamped on the frame this
        message reports, echoed back untouched. The server cannot
        compute round-trip time itself -- that would need the two clocks
        to agree on an epoch, and they do not. The phone subtracts the
        echo from its own clock, which is monotonic and only ever
        compared against itself, and reports the result back so the
        server's telemetry carries it too.
        """
        return {
            "type": "stats",
            "client_ms": client_ms,
            "x": None if self.position is None else round(self.position[0], 5),
            "y": None if self.position is None else round(self.position[1], 5),
            "received": self.received,
            "processed": self.processed,
            "dropped": self.dropped,
            "failed": self.failed,
            "decode_ms": round(self.decode_ms, 2),
            "solve_ms": round(self.solve_ms, 2),
            "round_trip_ms": round(self.round_trip_ms, 1),
            "markers_detected": self.markers_detected,
            "inside_hull": self.inside_hull,
            "outcome": self.outcome,
        }
