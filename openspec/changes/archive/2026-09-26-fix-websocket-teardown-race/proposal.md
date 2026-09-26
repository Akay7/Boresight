## Why

Several WebSocket tests fail intermittently with `CancelledError`
(`tests/test_stream_e2e.py` about one run in four,
`test_marker_source_routes.py::test_toggling_over_the_socket_is_remembered_too`,
`test_layout_source.py::test_the_frame_socket_works_under_an_on_screen_layout`).
The failures come from the frame session's teardown in `server.py`, not
from the tests: when the handler is cancelled while it waits for its own
tasks to wind down, it raises a cancellation that no longer carries the
canceller's identity, so the framework cannot recognise it as its own and
lets it escape. The same teardown also lets a frame already running on an
executor thread finish after the session has released the cursor, and
that late move takes a free cursor back for a session that is gone.

## What Changes

- The frame session's teardown waits for its tasks without re-raising a
  cancellation of its own making: a cancellation that reaches the handler
  during teardown is the one its canceller sent, so the server (or the
  test client) can tell it apart from a fault.
- A session's cursor gate is closed on disconnect, under the arbiter's
  lock: a frame still in the executor when the client leaves can finish,
  but its move never lands and never takes the cursor.
- The in-flight frame is waited for (shielded, not cancelled) during
  teardown, so a session's executor work does not outlive it unobserved.
- Trigger-hold release, cursor-ownership release and session
  unregistration stay synchronous and ahead of the first `await`.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `video-ingest`: "Disconnection leaves no motion and no leaked work"
  gains a scenario for a frame that is still being processed when the
  client disconnects, and states that the session gives up the cursor
  for good.

## Impact

- `src/boresight/server.py` (`run_frame_session` teardown).
- `src/boresight/shooter.py` (`CursorArbiter` / `_GatedCursor` gain a
  close).
- Tests: `tests/test_stream_e2e.py`, `tests/test_cursor_ownership.py` /
  `tests/test_shooter.py` gain regression tests.
- No API, protocol or dependency change.
