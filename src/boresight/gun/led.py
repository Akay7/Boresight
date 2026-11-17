"""What the status LED shows, as data, so nobody has to watch a LED to
test it."""

from __future__ import annotations

import enum
import threading
from typing import Protocol


class State(enum.Enum):
    STARTING = "starting"
    SEARCHING = "searching"  # running, no solved frame
    AIMING = "aiming"  # the latest frame solved
    ERROR = "error"


# (on_ms, off_ms) per cycle. Solid on means aiming; blinking means it
# needs something from you.
PATTERNS: dict[State, tuple[int, int]] = {
    State.STARTING: (100, 900),
    State.SEARCHING: (500, 500),
    State.AIMING: (1000, 0),
    State.ERROR: (100, 100),
}


def level_at(state: State, t_ms: float) -> bool:
    on_ms, off_ms = PATTERNS[state]
    if off_ms == 0:
        return True
    return (t_ms % (on_ms + off_ms)) < on_ms


class LedPin(Protocol):
    def set(self, on: bool) -> None: ...


class StatusIndicator:
    """Holds the state and drives a pin from it. With no pin it only logs
    changes, which is all a gun with no LED can do."""

    def __init__(self, pin: LedPin | None, log=None) -> None:
        self._pin = pin
        self._log = log
        self._state = State.STARTING
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def state(self) -> State:
        return self._state

    def set_state(self, state: State) -> None:
        if state is not self._state:
            self._state = state
            if self._log is not None:
                self._log(f"status: {state.value}")

    def start(self, now_ms=None) -> None:
        if self._pin is None:
            return
        import time

        clock = now_ms or (lambda: time.monotonic() * 1000)

        def run() -> None:
            while not self._stop.wait(0.02):
                self._pin.set(level_at(self._state, clock()))

        self._thread = threading.Thread(target=run, name="status-led", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        if self._pin is not None:
            self._pin.set(False)
