"""The transport layer between the phone's camera and the pipeline.

Four pieces, all independent of FastAPI so they can be tested without
a server: the frame message codec, the clock that turns a session's
capture timestamps into time for the aim filter, a single-slot mailbox
that drops stale frames, and the per-connection counters.

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
import math
import struct
import time
from collections.abc import Callable
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


class CaptureClock:
    """One session's capture timestamps, as seconds for the aim filter.

    The filter's interval between two frames should be how far apart
    they were *captured*, which only the client's clock knows. The
    server's clock at processing time adds every millisecond of Wi-Fi,
    slot and decode jitter to that interval, and the filter turns it
    into aim jitter.

    Client timestamps are only ever differenced against the same
    client's previous one. The first frame is placed at the server's
    clock, and each later one that far after the one before it. A step
    that cannot be a real frame interval -- not a number, not forward,
    or longer than `MAX_STEP_S` -- is replaced by the server's own
    interval since the last stamp, clamped to `[MIN_STEP_S,
    MAX_STEP_S]`, and the client timeline resumes from that frame. So
    whatever the client's clock does, time only moves forward, by a
    bounded amount: a zero or negative interval would spike the
    filter's speed estimate, and a clock jump is not an interval at all.
    """

    MIN_STEP_S = 0.001
    MAX_STEP_S = 1.0

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._last_client_ms: float | None = None
        self._last_t: float | None = None
        self._last_server: float | None = None
        self.fallbacks = 0

    def stamp(self, client_ms: float) -> float:
        server_now = self._clock()
        if self._last_t is None or self._last_server is None:
            t = server_now
        else:
            step = self._client_step(client_ms)
            if step is None:
                self.fallbacks += 1
                step = min(
                    self.MAX_STEP_S,
                    max(self.MIN_STEP_S, server_now - self._last_server),
                )
            t = self._last_t + step
        # Even an untrusted timestamp becomes the reference for the
        # next step: after a jump, the client's clock is right again
        # from here on, just from a different origin.
        self._last_client_ms = client_ms if math.isfinite(client_ms) else None
        self._last_t = t
        self._last_server = server_now
        return t

    def _client_step(self, client_ms: float) -> float | None:
        if self._last_client_ms is None or not math.isfinite(client_ms):
            return None
        step = (client_ms - self._last_client_ms) / 1000.0
        if not 0.0 < step <= self.MAX_STEP_S:
            return None
        return step


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
    triggers: int = 0

    # Who is on the other end, from its `hello`. None until it says:
    # more than one kind of device can stream now, and a log line that
    # says "phone" about an ESP32-CAM sends the operator to the wrong
    # device.
    client_kind: str | None = None
    client_version: str | None = None
    frame_size: tuple[int, int] | None = None

    # Whether this session drives the cursor: "yours", "other" or
    # "free" (see `shooter.CursorArbiter`). Set by the server per report.
    cursor: str | None = None

    # Per connection, never per app or per pipeline: one phone turning
    # the debug view on must not change what another phone receives, and
    # the pipeline behind them is shared.
    debug_enabled: bool = False
    debug: dict | None = None

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

        The debug geometry is keyed in only while this session has asked
        for it. A session that never asked gets a payload with no
        `debug` key at all rather than a null one, so a client written
        against the payload as it stands cannot begin half-rendering an
        overlay it never requested. Present-but-null says something
        different -- "you asked, and this frame has nothing to show" --
        and a client clears its overlay on it.
        """
        message = {
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
            "triggers": self.triggers,
            "cursor": self.cursor,
        }
        if self.debug_enabled:
            message["debug"] = self.debug
        return message


UNIDENTIFIED = "unidentified"


# Identity, not field equality: two fresh sessions from the same address
# compare equal field by field, and unregistering one must not remove
# the other.
@dataclass(eq=False)
class ActiveSession:
    address: str
    stats: SessionStats
    started: float

    def label(self) -> str:
        """How logs name this session: its kind once known, then where."""
        return f"{self.stats.client_kind or UNIDENTIFIED} {self.address}"


class SessionRegistry:
    """The frame sessions currently connected, for reading from outside.

    A client with no screen of its own -- an ESP32-CAM inside a gun
    shell -- cannot display its telemetry, so it has to be readable from
    another device. Entries are added when a session starts and removed
    when it ends, never retained: a listing that kept closed sessions
    would show a dead camera as streaming.

    Touched only from the event loop, so no locking.
    """

    def __init__(self) -> None:
        self._sessions: list[ActiveSession] = []

    def register(
        self, address: str, stats: SessionStats, started: float
    ) -> ActiveSession:
        session = ActiveSession(address, stats, started)
        self._sessions.append(session)
        return session

    def unregister(self, session: ActiveSession) -> None:
        if session in self._sessions:
            self._sessions.remove(session)

    def __len__(self) -> int:
        return len(self._sessions)

    def listing(self, now: float) -> list[dict]:
        """Each live session's identity and its latest telemetry.

        Debug geometry is left out: it is kilobytes per frame, describes
        an image nobody reading this can see, and belongs to the client
        that asked for it.
        """
        entries = []
        for session in self._sessions:
            stats = session.stats
            telemetry = stats.as_message()
            telemetry.pop("debug", None)
            entries.append(
                {
                    "address": session.address,
                    "client": stats.client_kind or UNIDENTIFIED,
                    "version": stats.client_version,
                    "frame_size": (
                        None if stats.frame_size is None else list(stats.frame_size)
                    ),
                    "connected_s": round(now - session.started, 1),
                    "stats": telemetry,
                }
            )
        return entries
