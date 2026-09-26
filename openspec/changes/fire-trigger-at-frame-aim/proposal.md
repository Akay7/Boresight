## Why

The trigger carries no position: the server clicks wherever the cursor
currently is, and the cursor is the *smoothed* aim, which on a fast
swing trails the real aim by a noticeable distance. Shots land behind
where the player was pointing at the moment they pulled the trigger.
The server already knows the unsmoothed aim of every frame it solved;
it just cannot tell which frame the shot belongs to.

## What Changes

- A trigger message (`{"type": "trigger"}` and `{"type": "trigger",
  "state": "down"}`) may carry `frame_ms`: the timestamp of the frame
  the shot was aimed with, in the same client clock as the frame header
  (the latest frame the client sent).
- The server keeps a short history of each session's unsmoothed solved
  aim points, keyed by client timestamp. For a shot with `frame_ms`, it
  waits (briefly, bounded) until that frame has been processed, moves
  the cursor to that frame's unsmoothed aim point, presses there, and
  then lets smoothing carry on from the next frame.
- A shot whose frame did not solve, or is not in the history, fires
  where the cursor is, exactly as today. A trigger without `frame_ms`
  behaves exactly as today, so older clients and already-flashed
  devices keep working.
- Press, release and click keep their order and their hold semantics:
  an `up` sent right after a `down` that is still waiting for its frame
  is applied after the press, never before it.
- The phone sends `frame_ms` with `down`. The ESP32-CAM firmware sends
  it with `down` too.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities
- `trigger-emission`: a trigger may name the frame it was aimed with,
  and then fires at that frame's unsmoothed aim point.
- `trigger-hold`: a `down` naming a frame presses at that frame's aim
  point; ordering of press and release is preserved while a press waits
  for its frame.
- `phone-client`: the on-screen trigger names the latest sent frame.

## Impact

- `src/boresight/shot.py` (new): aim history and the ordered queue of
  trigger actions waiting for their frame.
- `src/boresight/server.py`: trigger parsing, per-session history,
  running queued actions between frames and on a deadline.
- `src/boresight/web/capture.js`: `frame_ms` on `down`.
- `firmware/boresight-cam`: `bp_format_trigger_down`, a
  `link_send_trigger_down` that stamps the last frame sent on the
  current connection, and `buttons.c` using it; host test.
- Tests: `tests/test_shot.py` (new), `tests/test_stream_e2e.py`,
  `firmware/boresight-cam/test_host/test_proto.c`.
- Supersedes, for clients that send `frame_ms`, the pending
  `add-aim-smoothing` requirement "A trigger press fires at the smoothed
  position".
