## Context

`_handle_control` (`server.py`) turns a trigger message into
`TriggerHold.click()` / `acquire()` / `release()` on the raw cursor
backend the moment the text message is read in the receive loop. The
cursor at that moment is wherever `SmoothingCursorBackend` last put it:
the One Euro filter's output, which lags a fast swing by design. Each
processed frame's *unsmoothed* position is already in its `FrameResult`
(`position`) and reported to the client, but thrown away after the
report.

Frames and text messages share one ordered WebSocket, so by the time
the server reads a trigger, every frame the client sent before it has
already been received: it is either processed, in the session's
`FrameSlot`, being decoded/solved in the executor, or was dropped by the
slot in favour of a newer one. Since `use-capture-timestamps-for-smoothing`,
each frame's header timestamp is its capture time.

## Goals / Non-Goals

**Goals:**
- A shot lands at the unsmoothed aim of the frame the client names.
- Legacy triggers (no `frame_ms`) behave exactly as before.
- Press/release order and every trigger-hold guarantee survive.

**Non-Goals:**
- Choosing the frame on the server (e.g. "the frame the player was
  looking at"): the client knows what it sent; the server just looks
  it up.
- Interpolating between frames, or extrapolating the aim forward.
- Changing smoothing itself, or re-seeding the filter at the shot.
- Moving the cursor for a click while the button is held by anyone:
  that is a drag in progress, and jerking it would move what is being
  dragged.

## Decisions

### The client names the latest frame it sent
`frame_ms` is the header timestamp of the most recent frame the client
sent before the press. It is the closest frame to the moment of the
press that the server will ever see, and naming it by the timestamp the
client already stamps needs no new identifier. The phone keeps
`state.lastSentStamp` (added by the previous change to skip repeats)
and puts it on `down`. The ESP32 records the last successfully sent
frame's stamp inside `link.c`, per connection, and a new
`link_send_trigger_down()` formats and sends the `down` under the same
lock, so the stamp and the send cannot straddle a reconnect.

### A per-session history of unsmoothed aim, keyed by client timestamp
`shot.AimHistory` records `(client_ms, position | None)` for every
processed frame, trimmed to the last 1000 ms of client time (and at
most 64 entries). `aim_at(frame_ms)` returns the position of the solved
entry nearest to `frame_ms` and within 100 ms of it, or None. "Nearest
within 100 ms" rather than "exactly this frame" covers the frame having
been dropped by the newest-wins slot (the next processed frame is at
most a couple of frame periods later), and a named frame that failed to
solve mid-swing (a neighbour is still far better than the lagging
cursor). A client timestamp that goes backwards clears the history,
since it is a new timeline.

### Shots wait for their frame, bounded, in order
Trigger messages become `TriggerAction`s in a per-session
`TriggerQueue`. An action is ready when it names no frame, or when the
history's newest entry is at or after the named timestamp (the frame,
or a newer one that displaced it, has been processed). The queue only
ever runs from its head, so an `up` behind a waiting `down` waits too,
which keeps a quick tap a press-then-release.

The queue is drained:
- right away when a trigger message arrives, if no frame of this
  session is being processed at that moment;
- after each frame is processed (and its aim recorded);
- on a 250 ms deadline from the first action that had to wait. Past it
  the head actions run with whatever the history has, falling back to
  firing in place, so a shot naming a frame the server never processes
  (unreadable header, bogus timestamp) is late, never lost.

Draining only while this session has no frame in the executor means the
shot's move-then-press cannot interleave with this session's own
smoothed move from a worker thread. Moves from *other* sessions can
still interleave; that is the multi-shooter problem, handled by
`isolate-cursor-per-session`.

250 ms: processing a frame takes 10–40 ms, so a real frame resolves far
sooner; the bound only matters for a client that names a frame that
will not come, and it is well under the 2 s hold-idle window.

### The shot moves the raw backend, and smoothing carries on
The move goes to the unwrapped backend (`app.state.cursor_backend`),
not through `SmoothingCursorBackend`, so the filter never sees the shot
position and its state is unchanged. The next frame's smoothed move
takes the cursor back onto the smoothed trail. For a click this is
exactly "shot where aimed, cursor as before". For a held `down` the drag
starts at the shot point and then follows the smoothed aim, which can
be a short visible hop on a fast swing.

Alternative: re-seed the filter at the shot position so the drag
continues from there. Rejected for now: it would make the smoothed
cursor jump forward on every shot, and the brief is to let smoothing
continue. Easy to revisit if drags feel wrong.

The cursor is moved only when the action will actually press: a click
or `down` while the button is already held (by this or another session)
moves nothing, since it presses nothing.

### Parsing is strict and backward compatible
`frame_ms` must be an `int` or `float` (not `bool`) and finite;
anything else is treated as absent, the same "ignore what cannot be
read" posture as `rtt` and `hello`. A plain trigger with `frame_ms` is a
click at that frame; `up` ignores `frame_ms`.

## Risks / Trade-offs

- [A shot is delayed by up to one frame's processing time] → 10–40 ms
  against hundreds of milliseconds of smoothing lag on a fast swing; a
  legacy trigger is not delayed at all.
- [The drag origin hop described above] → Documented; revisit with
  filter re-seeding if it matters in practice.
- [Trigger count and the stats report now update when the action runs,
  not when the message is read] → Actions without `frame_ms` still run
  at once, so existing tests and clients see no difference.
- [Firmware cannot be compiled here (no ESP-IDF)] → The protocol
  formatter is covered by the host test; `link.c`/`buttons.c` changes
  are small and flagged for a device build.
