## Context

`MarkerSourceController` wraps the raw backend once in a
`SmoothingCursorBackend` and builds one `HoldingPipeline(AimPipeline)`
per marker source. `controller.pipeline` is that `HoldingPipeline`, and
every session's `process_loop` solves with it. So there is one filter,
one held position and one path to the cursor for all sessions, and
frames of different sessions are processed concurrently in the default
executor.

Two earlier changes shape this one. `use-capture-timestamps-for-smoothing`
made the frame's time an explicit argument
(`HoldingPipeline.process_frame(t=)`, `AimPipeline.process_frame(backend=)`),
so a pipeline no longer needs its own backend to be the one it emits to.
`fire-trigger-at-frame-aim` gave each session a `_SessionTriggers` that
moves "the cursor" to a shot's aim before pressing.

## Goals / Non-Goals

**Goals:**
- One rule, easy to state and to see on the phone, for whose aim moves
  the cursor.
- No cross-session state in the aim path: filter, hold and shot aim are
  per session.
- Frame handling and reporting for non-owners unchanged.

**Non-Goals:**
- Several cursors, or one cursor per session (one uinput pen exists).
- Changing the shared trigger button (trigger-hold's "holds from several
  sessions share one button" stands).
- Ownership for `POST /cursor/move`: an explicit request goes straight
  to the raw backend, as before.
- Showing ownership on the ESP32-CAM (it has only an LED); it is in its
  stats and in `GET /sessions`.

## Decisions

### The rule: the last to press, else the first to aim, lapsing after 1 s without aim
Pressing the trigger is the one unambiguous "I am shooting now" signal,
so it always takes the cursor. Without a press, the cursor is only
handed out when it is free, to the first session to produce an aim
point, so a player who is aiming is never interrupted by someone else
merely walking into view of the markers. The owner keeps the cursor as
long as moves keep reaching it; after `OWNER_IDLE_S` = 1 s with none,
it lapses. "Aim" here is anything the session's pipeline sends to the
cursor: solved frames and dropout-hold re-sends, so a session that loses
the markers keeps the cursor for the 0.75 s hold plus 1 s, then lets go.
A disconnect releases at once.

Alternatives considered:
- *First session with markers in view keeps it until it disconnects.*
  An idle phone on the table would own the cursor forever.
- *Most recent aim wins.* This is today's behaviour: two streams
  alternate frame by frame.
- *Ownership only by trigger press.* A lone phone would not move the
  cursor until its first shot, which is a surprising regression.

### `CursorArbiter` owns the rule; each session gets a gated cursor
`shooter.CursorArbiter(backend)` lives on `app.state` next to
`TriggerHold`. `cursor_for(owner, label)` returns a `CursorBackend` view
whose `move_absolute` asks the arbiter to move: under a lock, it moves
the raw backend and refreshes the owner's timestamp if `owner` holds the
cursor, or takes it if it is free or lapsed, and otherwise drops the
move. The check and the device write are under one lock because moves
come from executor threads of several sessions at once; a device write
is microseconds. `claim(owner, label)` takes the cursor unconditionally,
`release(owner)` frees it if held, and `status(owner)` answers
`yours`/`other`/`free`. Owners are compared by identity (the session's
`SessionStats`), like `TriggerHold`. Ownership changes are logged with
the session's label, so the server log says whose aim the cursor
follows.

Button methods on the gated view pass straight to the raw backend: the
button is `TriggerHold`'s business, not the arbiter's.

### Per-session `SessionPipeline`, with the controller handing out only the stateless solver
`MarkerSourceController` no longer holds a filter or a hold. It builds
one `AimPipeline(layout, raw backend)` per source and exposes it as
`controller.pipeline`: stateless, safe to share, swapped atomically on a
switch. `controller.session_pipeline(cursor)` returns a new
`SessionPipeline` for one session: a `SmoothingCursorBackend` over the
session's gated cursor, with a filter from `_aim_filter()` (same env
overrides as before), and a `HoldingPipeline` that it rebuilds whenever
the controller's current `AimPipeline` changes. That keeps both earlier
guarantees per session: the filter outlives a marker-source switch; the
held position does not.

A non-owner's frames still go through its own filter and hold: its
smoothed aim stays warm, so taking over starts at the new owner's own
smoothed position (a clean jump) rather than easing from the old
owner's position through a filter that has never seen this stream.

### Shots go through the same gate, after claiming
`_SessionTriggers` gets the session's gated cursor instead of the raw
backend, and a `claim` callback. A press (plain trigger, or a `down` this
session is not already holding) claims first, then moves to the shot's
aim through the gate, then presses. Release does not claim. A press
from B while A holds the button hands the cursor to B, and the held
button drags at B's aim from then on; that is the "last to press" rule
applied consistently, and holding the button together is already
trigger-hold's shared-button behaviour.

### `cursor` in every stats message
`SessionStats.cursor` is set from `arbiter.status(stats)` right before
each report. Always present (a small string, not gated behind a request
like debug geometry), because a client with no screen can still expose
it through `GET /sessions`, and the phone shows it as a "Cursor" row:
"this phone", "another device", or "free".

## Risks / Trade-offs

- [A player who looks away from the screen for over ~1.75 s loses the
  cursor to another aiming player] → Intended; pressing the trigger
  takes it back at once.
- [Test and code that reached into `controller.pipeline._backend` for
  the shared filter] → Updated: the filter is per session now; tests
  build a `SessionPipeline` or read the session's.
- [Every session runs its own filter even when not owning] → Cheap
  arithmetic per frame.
- [Behaviour with two real phones is untested on hardware] → Covered
  by e2e tests with two sockets and the recording backend; real-device
  check listed in tasks.

## Migration Plan

None. Wire additions are one new stats field that existing clients
ignore (the ESP32 parses only the fields it knows).
