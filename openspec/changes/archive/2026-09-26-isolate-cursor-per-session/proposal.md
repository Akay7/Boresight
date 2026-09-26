## Why

Every connected session feeds the same smoothing filter and the same
dropout hold, and every session's solved frames move the one OS cursor.
With two phones (or a phone and an ESP32-CAM) streaming at once, the
cursor jumps between their aim points frame by frame, and the filter
blends the two streams into a position neither is aiming at. Even one
idle phone lying on a table with the markers in view is enough to
fight a player.

## What Changes

- **Active shooter rule.** One session drives the cursor at a time. A
  session takes the cursor when it presses the trigger (a click or a
  `down`), even from another session. While nobody holds it — at
  startup, after the owner disconnects, or after the owner has not
  produced an aim for 1 second — the first session to produce an aim
  point takes it. The owner keeps it for as long as it keeps aiming.
- Other sessions' frames are still decoded, solved, smoothed and
  reported to their own client exactly as before; they just do not
  reach the cursor.
- Each session has its own smoothing filter and its own dropout hold,
  so a handover starts from the new owner's own smoothed aim instead of
  blending two streams. Smoothing still carries across a marker-source
  switch within a session.
- Each stats message says whether this session has the cursor
  (`"cursor": "yours" | "other" | "free"`), and the phone shows it in
  its telemetry list. `GET /sessions` shows it too, through the stats.
- The trigger button itself is unchanged: holds from several sessions
  still share the one button (trigger-hold).

## Capabilities

### New Capabilities
- `cursor-ownership`: which session's aim drives the cursor, how
  ownership passes between sessions, and per-session smoothing and
  hold state.

### Modified Capabilities
- `phone-client`: the phone shows whether it currently drives the
  cursor.

## Impact

- `src/boresight/shooter.py` (new): `CursorArbiter`, the active-shooter
  rule and a per-session gated cursor.
- `src/boresight/marker_source.py`: the controller hands out the current
  stateless `AimPipeline`; per-session `SessionPipeline` owns the filter
  and hold.
- `src/boresight/server.py`: per-session pipeline and gated cursor,
  claim on trigger press, release on disconnect, `cursor` in stats.
- `src/boresight/stream.py`: `cursor` field in the stats message.
- `src/boresight/web/index.html`, `capture.js`: a "Cursor" row.
- Tests: `tests/test_shooter.py` (new), `tests/test_marker_source.py`,
  `tests/test_cursor_move.py`, `tests/test_cursor_ownership.py` (new),
  `tests/test_stream_e2e.py`.
- Supersedes the pending `add-aim-smoothing` and
  `add-aim-hold-on-dropout` design choice of one controller-wide filter
  and hold: both become per session.

## Spec reconciliation (added at archive time)

`add-aim-smoothing` and `add-aim-hold-on-dropout` were archived just
before this change, so their requirements are now in `openspec/specs/`.
This change's deltas therefore also modify `aim-hold` ("A brief dropout
re-sends the last solved position": the hold is per session and reaches
the cursor only through ownership) and `video-ingest` ("Streamed camera
frames drive the aim pipeline" and "Streaming produces the same result
as replaying the same frames": a streamed frame's move goes through the
session's smoothing and ownership, and streaming is compared with
replay on the solved positions reported, which is what
`tests/test_stream_e2e.py` asserts).
