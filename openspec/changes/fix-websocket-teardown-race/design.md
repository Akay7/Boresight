## Context

`run_frame_session` runs three tasks per connection (receiver, processor,
hold watchdog). The processor hands each frame to the default executor
(`loop.run_in_executor(None, _decode_and_solve, ...)`), where the
session's `SessionPipeline` solves it and, through the session's gated
cursor, may move the OS cursor. On disconnect the `finally` block cancels
the three tasks, releases the trigger hold and the cursor, unregisters
the session, and last of all does
`await asyncio.gather(receiver, processor, watchdog, return_exceptions=True)`.

### Reproduction

Before the fix, 30 runs of `tests/test_stream_e2e.py
tests/test_marker_source_routes.py tests/test_layout_source.py`
(88 tests each) failed 3 times; 40 runs of `tests/test_stream_e2e.py`
alone failed 8 times. Every failure was the same: the test's
`with client.websocket_connect(...)` block raised
`concurrent.futures.CancelledError` from `fut.result()` in Starlette's
`WebSocketTestSession.__exit__`. A pytest plugin wrapping anyio's
`BlockingPortal._call_func` captured where the cancellation escaped the
portal task (every one of 9 captures was identical):

```
File ".../starlette/testclient.py", line 145, in _run
    await self.app(self.scope, receive_rx.receive, send_tx.send)
  ...
File "src/boresight/server.py", line 655, in run_frame_session
    await asyncio.gather(receiver, processor, watchdog, return_exceptions=True)
File "src/boresight/server.py", line 580, in hold_watchdog
    await asyncio.sleep(HOLD_CHECK_INTERVAL_S)
asyncio.exceptions.CancelledError
```

### Root cause

The test client's `__exit__` sends `websocket.disconnect` and then at
once cancels the anyio `CancelScope` wrapping the app. When that cancel
lands while the handler is parked on the final `gather`, the task's
cancellation is forwarded to the gather future, and gather's rule is to
raise *the cancellation error of a child* -- here one created by our own
`watchdog.cancel()`, with no message. anyio decides whether a
`CancelledError` is its own by the message it put on the cancel
("Cancelled via cancel scope ..."); the child's message-less one is not,
so the scope refuses to swallow it and it escapes as a failure. The
tests were fine; the server raised a cancellation that looked foreign.
Under uvicorn the same race makes a server shutdown during a session's
teardown surface an error instead of a clean cancel.

Reading the teardown for the ticket's other suspicion found a second,
real leak: `processor.cancel()` cancels only the asyncio wrapper of the
executor job. The thread carries on, and when it finishes the solve it
calls the session's gated cursor, which calls `CursorArbiter.move`. By
then `arbiter.release(stats)` has run, the cursor is free, and a free
cursor goes to whoever aims first -- so the dead session takes it back
and holds everyone else off for `OWNER_IDLE_S`, and the cursor jumps to
a position the client never saw.

## Goals / Non-Goals

**Goals:**
- A cancellation arriving during teardown propagates as the canceller's
  own, so anyio / uvicorn recognise it.
- No cursor move from a session after its teardown began, even from a
  frame already on an executor thread.
- Hold release, cursor release and unregistration stay synchronous and
  ahead of the first `await`, as before.

**Non-Goals:**
- Interrupting an executor job. A solve is tens of milliseconds and
  Python threads cannot be cancelled; it is allowed to finish.
- Changing the test client or pinning Starlette/anyio.

## Decisions

### Wait with `asyncio.wait`, not `gather`
The final wait becomes `asyncio.wait(...)` over whatever is still
pending, followed by retrieving each finished task's exception (what
`return_exceptions=True` used to do for us, so nothing logs "exception
was never retrieved"). `asyncio.wait` does not cancel its awaitables
when the waiter is cancelled and re-raises the waiter's own
`CancelledError`, which carries the canceller's message.
*Alternatives:* `contextlib.suppress(CancelledError)` around the gather
would swallow the server's real shutdown cancellation too, and anyio
re-delivers a scope cancel until the task leaves the scope, so
swallowing just delays it; `asyncio.shield(gather(...))` still raises a
fresh message-less error from the shield. The cancellations the handler
itself caused (its three tasks) are absorbed, because they are only
ever inspected, never re-raised; the one sent from outside is passed on
untouched -- that is the split the ticket asks for between "the
cancellation that belongs to the closing socket" and everyone else's.

### Close the session's cursor gate under the arbiter's lock
`_GatedCursor` gains `close()`: under the arbiter's lock it marks the
gate closed and frees the cursor if this session owns it; `move_absolute`
checks the flag under the same lock before moving. A move that is past
the check already holds the lock, so `close()` waits for it and then
frees the cursor; a move that comes after sees the gate closed and does
nothing. The server calls `cursor.close()` where it used to call
`arbiter.release(stats)`. *Alternative:* only awaiting the in-flight
job and releasing again afterwards -- but that await can itself be
cancelled (server shutdown), which leaves the leak in exactly the case
nobody is watching, and moves the release after an `await`.

### Keep the in-flight job observable, and wait for it
The processor now awaits `asyncio.shield(job)` on the executor future
and keeps it in `in_flight`. Cancelling the processor no longer cancels
the job's future, so teardown can include it in the final
`asyncio.wait` and the handler returns only after the session's last
solve is done. A done-callback retrieves the job's exception, so a job
that fails after its session was cancelled is not reported as an
unretrieved exception. With the gate closed, waiting is not needed for
correctness; it keeps "the session's work ends with the session" true,
which is what the spec says and what lets a test assert on the backend
right after the socket closes.

### Tests
Regression tests for both defects:
- `tests/test_shooter.py`: a closed gate drops moves, frees the cursor
  it owned, and leaves another owner's cursor alone.
- `tests/test_stream_e2e.py`: a frame held in the executor (the solve is
  blocked on an event) when the client disconnects finishes after the
  disconnect without moving the cursor, and the cursor is free; and
  a teardown cancelled while waiting raises the canceller's
  cancellation (a direct `run_frame_session` test with a fake socket,
  asserting the escaping `CancelledError` carries the message passed to
  `task.cancel`).

The three flaky tests named in the ticket had no race of their own;
none needed changing.

## Risks / Trade-offs

- [The handler now waits for an in-flight solve before returning] → one
  frame's processing time, tens of milliseconds; a server shutdown can
  still cancel the wait, and the gate makes that harmless.
- [The gate reaches into the arbiter's private lock] → both live in
  `shooter.py`, and the existing `_GatedCursor` already reaches into the
  backend the same way; the alternative (a public "move unless closed"
  API) would exist for this one caller.

## Verification

All runs on Python 3.14, `uv run pytest -q -p no:cacheprovider`, on the
same machine.

| Run | Before | After |
|---|---|---|
| `test_stream_e2e.py` + `test_marker_source_routes.py` + `test_layout_source.py` (88 tests; 102 after, with `test_shooter.py` and the new tests) | 3 of 30 runs failed | 0 of 60 runs failed |
| `test_stream_e2e.py` alone | 8 of 40 runs failed | 0 of 50 runs failed |
| Full suite | 1 of 10 runs failed (`test_a_dropout_after_a_solve_is_still_reported_as_unsolved`) | 0 of 5 runs failed (574 passed, 7 skipped each) |

Before-fix failures were spread over whichever test's socket happened to
close mid-wait (`test_a_silent_holding_session_is_released`,
`test_a_corrupt_frame_reports_no_geometry`,
`test_every_streamed_frame_is_solved_and_reported`,
`test_a_streaming_session_can_hold_past_the_idle_window`, ...), all with
the traceback above. The two new end-to-end tests
(`test_a_frame_finishing_after_disconnect_does_not_take_the_cursor`,
`test_a_teardown_cancelled_mid_wait_raises_the_cancellers_cancellation`)
fail against the old `server.py`/`shooter.py` and pass after.
