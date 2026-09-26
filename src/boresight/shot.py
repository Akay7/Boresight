"""Firing the trigger where the player aimed, not where the cursor lags.

The cursor shows the *smoothed* aim, which trails a fast swing by
design. A trigger that clicks wherever the cursor happens to be lands
behind the shot. So a client names the frame it was aiming with -- by
the timestamp it stamped on that frame -- and the server fires at that
frame's unsmoothed aim point instead.

Two pieces, both per session and both free of FastAPI and devices so
they can be tested alone: `AimHistory` remembers recent unsmoothed aim
points by client timestamp, and `TriggerQueue` keeps a session's trigger
actions in the order they were sent until the frame each one names has
been processed.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Literal

Point = tuple[float, float]

# How much client time of aim to keep. A shot names the latest frame
# sent, which the server has already received when the trigger arrives,
# so anything older than this is never asked for.
HISTORY_MS = 1000.0
HISTORY_MAX_ENTRIES = 64

# How far from the named frame a solved neighbour may be and still stand
# in for it: the named frame may have been dropped by the newest-wins
# slot, or may itself have failed to solve mid-swing. Two to three frame
# periods; beyond that, the lagging cursor is no worse a guess.
MATCH_MS = 100.0

TriggerState = Literal["click", "down", "up"]


class AimHistory[T]:
    """Recent unsmoothed aim points, keyed by the client's timestamps.

    `T` is what is remembered per frame: an aim point to fire at, or,
    for zeroing, the frame's whole geometry (`zeroing.SightFrame`).
    """

    def __init__(
        self, span_ms: float = HISTORY_MS, max_entries: int = HISTORY_MAX_ENTRIES
    ) -> None:
        self._span_ms = span_ms
        self._entries: deque[tuple[float, T | None]] = deque(maxlen=max_entries)

    @property
    def newest_ms(self) -> float | None:
        return self._entries[-1][0] if self._entries else None

    def record(self, client_ms: float, position: T | None) -> None:
        """One processed frame: its aim, or None if it did not solve."""
        if not math.isfinite(client_ms):
            return
        newest = self.newest_ms
        if newest is not None and client_ms < newest:
            # The client's clock went backwards: a new timeline, against
            # which nothing already here can be compared.
            self._entries.clear()
        self._entries.append((client_ms, position))
        while self._entries and self._entries[0][0] < client_ms - self._span_ms:
            self._entries.popleft()

    def covers(self, frame_ms: float) -> bool:
        """Whether the named frame, or a later one, has been processed."""
        newest = self.newest_ms
        return newest is not None and newest >= frame_ms

    def aim_at(self, frame_ms: float, tolerance_ms: float = MATCH_MS) -> T | None:
        """The solved aim nearest `frame_ms`, if one is close enough."""
        best: T | None = None
        best_distance = tolerance_ms
        for client_ms, position in self._entries:
            if position is None:
                continue
            distance = abs(client_ms - frame_ms)
            if distance <= best_distance:
                best, best_distance = position, distance
        return best


@dataclass(frozen=True)
class TriggerAction:
    """One trigger message, as it will be acted on.

    `frame_ms` names the frame a press was aimed with; None fires where
    the cursor is, as a trigger always did before frames could be named.
    """

    state: TriggerState
    frame_ms: float | None = None


class TriggerQueue:
    """A session's trigger actions, in the order the client sent them.

    Only the head can run. A press waiting for its frame therefore holds
    back an `up` sent right after it, so a quick tap is still a press
    followed by a release, never the other way round.
    """

    def __init__(self) -> None:
        self._actions: deque[TriggerAction] = deque()

    def __len__(self) -> int:
        return len(self._actions)

    def push(self, action: TriggerAction) -> None:
        self._actions.append(action)

    def ready(self, history: AimHistory, *, force: bool = False) -> list[TriggerAction]:
        """Take the leading actions that can run now.

        `force` takes everything, waiting or not: past the deadline, a
        shot fires with whatever the history has rather than not at all.
        """
        taken = []
        while self._actions:
            head = self._actions[0]
            waiting = head.frame_ms is not None and not history.covers(head.frame_ms)
            if waiting and not force:
                break
            taken.append(self._actions.popleft())
        return taken

    def clear(self) -> None:
        self._actions.clear()
