"""Which session's aim drives the one OS cursor: the active shooter.

There is one virtual pen and possibly several cameras. Left alone, every
session's solved frames move it, and with two streams at once the
cursor alternates between their aim points frame by frame. So one
session owns the cursor at a time:

- pressing the trigger takes it, from anyone -- the one unambiguous
  "I am shooting now";
- otherwise, a free cursor goes to the first session to aim at the
  screen, so a player already aiming is never interrupted by someone
  merely walking into view of the markers;
- the owner keeps it for as long as its aim keeps arriving, and loses it
  once none has for `OWNER_IDLE_S`, or at once when it disconnects.

Other sessions' frames are still solved, smoothed and reported to their
own client; their moves just stop at the gate.

Owners are compared by identity -- the server uses each session's
`SessionStats`, as `TriggerHold` does -- and need not be hashable.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Literal

from boresight.inject import CursorBackend

# How long the owner may go without aiming before the cursor is free.
# "Aiming" is anything the session's pipeline sends to the cursor,
# including the dropout hold's re-sends, so a session that loses the
# markers keeps the cursor for the hold window plus this. Long enough to
# outlast a brief occlusion; short enough that a player who has put the
# gun down does not hold everyone else off.
OWNER_IDLE_S = 1.0

CursorStatus = Literal["yours", "other", "free"]

logger = logging.getLogger("boresight")


class CursorArbiter:
    """Hands the cursor to one session at a time.

    Moves arrive from executor threads of several sessions at once, so
    the ownership check and the device write happen under one lock: a
    session that has just lost the cursor cannot land one last move
    after the new owner's.
    """

    def __init__(
        self,
        backend: CursorBackend,
        idle_s: float = OWNER_IDLE_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._backend = backend
        self._idle_s = idle_s
        self._clock = clock
        self._lock = threading.Lock()
        self._owner: object | None = None
        self._last_aim = 0.0

    def cursor_for(self, owner: object, label: Callable[[], str]) -> _GatedCursor:
        """The cursor as `owner` sees it: its moves land only while it
        owns the cursor, or when taking a free one, until the view is
        closed. `label` names the session in the log line when ownership
        changes."""
        return _GatedCursor(self, owner, label)

    def claim(self, owner: object, label: Callable[[], str]) -> None:
        """Take the cursor for `owner`, whoever had it."""
        with self._lock:
            self._take(owner, label)

    def release(self, owner: object) -> None:
        """Free the cursor if `owner` has it. Nothing otherwise."""
        with self._lock:
            self._release_locked(owner)

    def status(self, owner: object) -> CursorStatus:
        with self._lock:
            current = self._current()
        if current is None:
            return "free"
        return "yours" if current is owner else "other"

    def move(self, owner: object, label: Callable[[], str], x: float, y: float) -> bool:
        """Move for `owner` if it may; whether the move landed."""
        with self._lock:
            return self._move_locked(owner, label, x, y)

    def _move_locked(
        self, owner: object, label: Callable[[], str], x: float, y: float
    ) -> bool:
        current = self._current()
        if current is not owner:
            if current is not None:
                return False
            self._take(owner, label)
        self._last_aim = self._clock()
        self._backend.move_absolute(x, y)
        return True

    def _release_locked(self, owner: object) -> None:
        if self._owner is owner:
            self._owner = None

    def _current(self) -> object | None:
        """The owner, unless it has lapsed. Called with the lock held."""
        if self._owner is not None and self._clock() - self._last_aim > self._idle_s:
            self._owner = None
        return self._owner

    def _take(self, owner: object, label: Callable[[], str]) -> None:
        # Refreshed on a claim too: a press counts as aiming, so the new
        # owner is not lapsed before its first frame arrives.
        self._last_aim = self._clock()
        if self._owner is owner:
            return
        self._owner = owner
        logger.info("cursor now follows %s", label())


class _GatedCursor:
    """One session's view of the cursor, behind its `CursorArbiter`.

    Buttons pass straight through: holding the button is `TriggerHold`'s
    business, and it is shared by every session on purpose.

    Closed when its session ends. A frame can still be on an executor
    thread then, and its move would otherwise find the cursor just
    freed and take it back for a session that is gone.
    """

    def __init__(
        self, arbiter: CursorArbiter, owner: object, label: Callable[[], str]
    ) -> None:
        self._arbiter = arbiter
        self._owner = owner
        self._label = label
        self._closed = False

    def move_absolute(self, x: float, y: float) -> None:
        # The flag is read under the arbiter's lock, so a move is either
        # wholly before `close()` -- which then frees the cursor it took
        # -- or dropped.
        with self._arbiter._lock:  # noqa: SLF001 - its own gate
            if not self._closed:
                self._arbiter._move_locked(self._owner, self._label, x, y)  # noqa: SLF001

    def close(self) -> None:
        """Drop every move from now on, and free the cursor if it is ours."""
        with self._arbiter._lock:  # noqa: SLF001
            self._closed = True
            self._arbiter._release_locked(self._owner)  # noqa: SLF001

    def click(self) -> None:
        self._arbiter._backend.click()  # noqa: SLF001 - its own gate

    def press(self) -> None:
        self._arbiter._backend.press()  # noqa: SLF001

    def release(self) -> None:
        self._arbiter._backend.release()  # noqa: SLF001
