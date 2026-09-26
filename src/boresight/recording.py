"""The last few seconds of a session, kept so they can be saved.

A misbehaviour seen on real hardware is only a description until it can
be replayed. Each frame session keeps a rolling window of what it
received -- the JPEG payloads, their capture timestamps, the trigger
presses, and what the live pipeline made of each frame -- and on
request writes it out in the layout the checked-in fixtures already
use, so `pipeline.replay()` and the tests read a recording unchanged.

Buffering is references, not copies: the payload `bytes` the server
already holds are kept alive a little longer, and nothing is decoded or
re-encoded until a save. The window is bounded twice, by age and by
retained bytes, so a client streaming unexpectedly large frames costs a
shorter window rather than unbounded memory.

Nothing here ever stores a raw control message. The token travels only
in the handshake -- query string, header or cookie -- which this module
never sees, and control messages are reduced to the few fields a
recording needs before they are kept.
"""

from __future__ import annotations

import json
import math
import time
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from boresight.marker_map import MarkerMap
from boresight.markers import layout_toml

DEFAULT_RECORD_SECONDS = 10.0
DEFAULT_RECORD_MAX_BYTES = 64 * 1024 * 1024

# Next to the generated certificate, under a directory that is already
# gitignored: a recording is whatever the camera saw, and does not
# belong in a commit by accident.
DEFAULT_RECORDINGS_DIR = Path(".boresight") / "recordings"

FORMAT_VERSION = 1

# Longest client kind or version kept, as in the server's own `hello`.
_FIELD_MAX = 64


class NothingToRecordError(ValueError):
    """Raised for a save with no frames to write, or recording disabled."""


@dataclass(frozen=True)
class RecordingConfig:
    """How much each session keeps, and where saves go.

    A window of zero disables recording outright: sessions get no
    buffer at all, rather than an empty one they keep evicting into.
    """

    seconds: float = DEFAULT_RECORD_SECONDS
    max_bytes: int = DEFAULT_RECORD_MAX_BYTES
    root: Path = DEFAULT_RECORDINGS_DIR

    @property
    def enabled(self) -> bool:
        return self.seconds > 0 and self.max_bytes > 0


@dataclass(slots=True)
class _Frame:
    client_ms: float
    payload: bytes
    # The layout the session was solving against when this arrived.
    # A reference, so a marker-source switch inside the window can be
    # detected at save time by identity.
    layout: MarkerMap
    received: float
    live: dict | None = None


@dataclass(frozen=True)
class RecordingSnapshot:
    """A save's view of the buffer, taken on the event loop.

    Lists of references, so frames arriving while the snapshot is being
    written neither block on it nor change it.
    """

    frames: list[_Frame]
    triggers: list[dict]
    client: dict
    config: RecordingConfig


@dataclass(frozen=True)
class SavedRecording:
    path: Path
    frames: int
    omitted: int
    seconds: float

    def as_message(self) -> dict:
        return {
            "type": "recording",
            "path": str(self.path),
            "frames": self.frames,
            "omitted": self.omitted,
            "seconds": self.seconds,
        }


class FrameRecorder:
    """One session's rolling window. Touched only from the event loop."""

    def __init__(
        self, config: RecordingConfig, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._config = config
        self._clock = clock
        self._frames: deque[_Frame] = deque()
        self._triggers: deque[dict] = deque()
        self._bytes = 0
        self._client: dict = {}

    @property
    def retained_bytes(self) -> int:
        return self._bytes

    def __len__(self) -> int:
        return len(self._frames)

    def frame(self, client_ms: float, payload: bytes, layout: MarkerMap) -> None:
        now = self._clock()
        self._frames.append(_Frame(client_ms, payload, layout, now))
        self._bytes += len(payload)
        self._evict(now)

    def result(
        self,
        client_ms: float,
        outcome: str | None,
        position: tuple[float, float] | None,
    ) -> None:
        """Attach what the live pipeline made of the frame stamped `client_ms`.

        Searched from the newest end: the frame just processed is almost
        always the last one received, or one before it.
        """
        for entry in reversed(self._frames):
            if entry.client_ms == client_ms and entry.live is None:
                entry.live = {
                    "outcome": outcome,
                    "position": (
                        None
                        if position is None
                        else [round(position[0], 5), round(position[1], 5)]
                    ),
                }
                return

    def control(self, text: str | None) -> None:
        """Keep what a recording needs from one control message, and no more.

        Triggers become `{state, frame_ms, received}`; a `hello` updates
        the client's identity. Everything else, including the text
        itself, is dropped.
        """
        if not text:
            return
        try:
            message = json.loads(text)
        except ValueError:
            return
        if not isinstance(message, dict):
            return
        kind = message.get("type")
        if kind == "trigger":
            state = message.get("state")
            now = self._clock()
            self._triggers.append(
                {
                    "state": state if state in ("down", "up") else "click",
                    "frame_ms": _finite(message.get("frame_ms")),
                    "received": now,
                }
            )
            self._evict(now)
        elif kind == "hello":
            client = message.get("client")
            version = message.get("version")
            frame_size = message.get("frame_size")
            self._client = {
                "client": client[:_FIELD_MAX] if isinstance(client, str) else None,
                "version": version[:_FIELD_MAX] if isinstance(version, str) else None,
                "frame_size": (
                    frame_size
                    if isinstance(frame_size, list)
                    and len(frame_size) == 2
                    and all(type(side) is int for side in frame_size)
                    else None
                ),
            }

    def snapshot(self) -> RecordingSnapshot:
        self._evict(self._clock())
        return RecordingSnapshot(
            frames=list(self._frames),
            triggers=list(self._triggers),
            client=dict(self._client),
            config=self._config,
        )

    def _evict(self, now: float) -> None:
        horizon = now - self._config.seconds
        frames = self._frames
        while frames and (
            frames[0].received < horizon or self._bytes > self._config.max_bytes
        ):
            self._bytes -= len(frames.popleft().payload)
        while self._triggers and self._triggers[0]["received"] < horizon:
            self._triggers.popleft()


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def _image_size(payload: bytes) -> list[float] | None:
    frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return None
    height, width = frame.shape[:2]
    return [float(width), float(height)]


def _new_directory(root: Path, now: datetime) -> Path:
    """A directory no earlier save has used, named by the time.

    Created exclusively, so two saves in the same second get two
    directories rather than one merged one.
    """
    root.mkdir(parents=True, exist_ok=True)
    stem = now.strftime("%Y%m%d-%H%M%S")
    for attempt in range(1, 1000):
        path = root / (stem if attempt == 1 else f"{stem}-{attempt}")
        try:
            path.mkdir()
        except FileExistsError:
            continue
        return path
    raise FileExistsError(f"no free recording directory for {stem} under {root}")


def save_recording(
    snapshot: RecordingSnapshot,
    marker_source: dict | None = None,
    now: datetime | None = None,
) -> SavedRecording:
    """Write a snapshot as a replayable frame sequence.

    Blocking file I/O; the server calls it on a worker thread. The
    manifest is written last, so a directory without one is a save that
    did not finish.
    """
    if not snapshot.frames:
        raise NothingToRecordError("no frames received in the recording window yet")

    # One layout per recording: the newest frame's. Earlier frames
    # solved against another (a marker-source switch mid-window) would
    # replay against tags that were not there, so they are left out and
    # counted rather than silently mis-solved.
    layout = snapshot.frames[-1].layout
    frames = [entry for entry in snapshot.frames if entry.layout is layout]
    omitted = len(snapshot.frames) - len(frames)

    now = now or datetime.now().astimezone()
    directory = _new_directory(snapshot.config.root, now)
    origin = frames[0].received

    entries = []
    for index, entry in enumerate(frames, start=1):
        name = f"frame_{index:04d}.jpg"
        # Byte for byte what the client sent: a re-encode would change
        # what the detector sees.
        (directory / name).write_bytes(entry.payload)
        entries.append(
            {
                "frame": index,
                "file": name,
                "client_ms": entry.client_ms,
                "received_s": round(entry.received - origin, 4),
                "live": entry.live or {"outcome": "dropped", "position": None},
            }
        )
    if frames[-1].live is None:
        # The newest may simply still be on the executor.
        entries[-1]["live"] = {"outcome": "pending", "position": None}

    (directory / "markers.toml").write_text(
        layout_toml(layout, f"Marker layout in use when recorded {now.isoformat()}.")
    )

    sizes = Counter(marker.size_mm for marker in layout.markers.values())
    image_size = _image_size(frames[-1].payload)
    if image_size is None and snapshot.client.get("frame_size"):
        image_size = [float(side) for side in snapshot.client["frame_size"]]

    manifest = {
        # The keys the fixture manifests carry, so the same readers work.
        "image_size": image_size,
        "screen_size_mm": list(layout.screen_size_mm),
        # The commonest size; `markers.toml` has each marker's own.
        "marker_size_mm": sizes.most_common(1)[0][0],
        "marker_layout_mm": {
            str(marker_id): [marker.x_mm, marker.y_mm]
            for marker_id, marker in sorted(layout.markers.items())
        },
        "frames": entries,
        # Recording-only context. `received_s` counts from the first
        # saved frame's arrival on the server's clock; `client_ms` and
        # `frame_ms` are the client's own clock, comparable only with
        # each other.
        "recording": {
            "format_version": FORMAT_VERSION,
            "saved_at": now.isoformat(),
            "window_s": snapshot.config.seconds,
            "max_bytes": snapshot.config.max_bytes,
            "omitted_frames": omitted,
            "client": snapshot.client or None,
            "marker_source": marker_source,
            "layout_file": "markers.toml",
        },
        "triggers": [
            {
                "state": trigger["state"],
                "frame_ms": trigger["frame_ms"],
                "received_s": round(trigger["received"] - origin, 4),
            }
            for trigger in snapshot.triggers
        ],
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    # Absolute: it is read on the phone, far from the server's working
    # directory, and pasted into a replay command on the PC.
    return SavedRecording(
        path=directory.resolve(),
        frames=len(frames),
        omitted=omitted,
        seconds=round(frames[-1].received - origin, 1),
    )


def recording_request(text: str | None) -> bool:
    """Whether a control message asks for the session to be saved."""
    if not text or '"record"' not in text:
        return False
    try:
        message = json.loads(text)
    except ValueError:
        return False
    return isinstance(message, dict) and message.get("type") == "record"
