## Context

Everything the trigger needs already exists in skeleton form:
`video-ingest`'s frame WebSocket reserves its text channel for "JSON
control and telemetry" precisely so a trigger event needs no second
connection (`stream.py` module docstring, `server.py`'s
`_handle_control`), and `cursor-injection`'s `UinputCursorBackend`
already owns the one virtual input device the OS sees. The gap is
narrow: a control-message case, a backend operation, and a phone-side
button. This is a small cross-cutting change (phone client → WebSocket
control channel → cursor backend → OS), which is why it gets a design
doc despite its size.

## Goals / Non-Goals

**Goals:**
- A tap on the phone's trigger button reaches the OS as a real, discrete
  left-click — usable by anything that takes mouse input (MAME,
  emulators, README's "anything with mouse aim"), distinct from the
  continuous positioning traffic `move_absolute` already generates.
- No new connection, endpoint, or wire format: the trigger rides the
  existing frame WebSocket's text channel exactly as `video-ingest`
  already reserved it.
- The trigger button is unusable (and says so) before streaming starts,
  since there is no connection to send it on.

**Non-Goals:**
- Held-trigger / full-auto behavior. README describes a tap producing a
  click, singular; a press-and-hold state machine is a different
  feature and not something any current consumer needs.
- Aiming logic changes. The click fires at wherever the cursor already
  is from the last `move_absolute` call; the trigger does not carry or
  request a position of its own.
- Windows input backend — out of scope same as it is for
  `cursor-injection` generally.

## Decisions

**`click()` as a new one-shot operation on `CursorBackend`, not a
down/up pair.** The protocol gains `click() -> None`, implemented as a
complete press-then-release, mirroring how `move_absolute` already
performs a complete press-move-release per call rather than exposing
separate down/move/up primitives. Consistent with the Non-Goal above:
nothing today needs a sustained button state, and a single atomic
operation is simpler to reason about, order against concurrent
`move_absolute` calls, and test.

**Click uses `BTN_LEFT` on a second, dedicated `uinput` device, not the
one `move_absolute` already uses.** `BTN_LEFT` is what mouse-driven
light-gun software (MAME's `-lightgun`, generic mouse-aim emulators)
already listens for, so it needs no game-side configuration to work,
and it is a distinct code from `BTN_TOUCH` — `move_absolute` already
performs a full `BTN_TOUCH` down/up on every call as a *side effect of
moving* (the "synthetic tap" the existing code comment describes), so
reusing that code for the trigger would make a genuine trigger pull
indistinguishable from ordinary cursor tracking, which happens dozens
of times a second.
Adding `BTN_LEFT` to the *same* device was tried first, since it keeps
one virtual device to manage — but verified against a live X11 session
(querying the created device's udev properties directly, before ever
emitting an event) that doing so changes the device's classification
from `ID_INPUT_TOUCHSCREEN` to `ID_INPUT_MOUSE`, the same regression
`cursor-injection`'s original design flagged as the risk of combining
`ABS_X/Y` with `BTN_LEFT`. That would send `move_absolute`'s
positioning back through relative-motion acceleration instead of the
direct placement `BTN_TOUCH` + `INPUT_PROP_DIRECT` earns it — confirmed
as the *only* combination among the three tested that keeps the
touchscreen tag. So `click()` lives on a second `UInput` device
carrying only `BTN_LEFT` — no `ABS`/`REL` axes at all. Verified (via
Xlib, querying the X core pointer's button mask before/after a write)
that this button-only device delivers a real press/release to the
shared core pointer with no effect on its position, since position and
button state are properties of the one core pointer the OS exposes,
independent of which device reported which. Both devices are opened
together at construction and closed together; `click()` never touches
the positioning device and `move_absolute` never touches the click
device.

**The trigger control message is a bare `{"type": "trigger"}`, with no
payload.** `rtt` needs a measured value; a click needs nothing beyond
"it happened" — the position is already wherever the last processed
frame put it. Keeping it payload-free means there is nothing to
validate or reject, matching `_handle_control`'s existing pattern of
silently ignoring anything it doesn't recognize.

**`_handle_control` gains a cursor-backend parameter.** Today it only
closes over `SessionStats`. Reaching the backend requires passing it
through (from `websocket.app.state.cursor_backend`, the same instance
`get_cursor_backend` already resolves for `/cursor/move`) alongside
`stats`, threaded through `run_frame_session`'s existing call site.

**A `triggers` counter joins `SessionStats`, reported in the same
telemetry message as everything else.** The phone has no other way to
confirm a tap actually reached the server — same reasoning
`phone-client`'s existing "Connection state and telemetry are visible
on the phone" requirement already gives for round-trip time and frame
counts. Added as a plain counter alongside `received`/`processed`, not
a new message type.

**The phone button fires on `pointerdown`, not `click`.** A `click`
event waits for pointerup and (on touch) the browser's tap-recognition
delay; a trigger should feel immediate. `touch-action: none` on the
button prevents the browser from interpreting the press as the start of
a scroll/zoom gesture first. Disabled until `state.socket` is open,
matching how `els.start` is already managed.

## Risks / Trade-offs

[Adding `BTN_LEFT` to the existing `BTN_TOUCH` + `INPUT_PROP_DIRECT`
device changes its udev/libinput classification and would regress
`move_absolute`'s already-verified direct positioning] → Confirmed
during implementation (see Decisions): resolved by using a second
`UInput` device carrying only `BTN_LEFT` for `click()`, leaving the
positioning device's capabilities exactly as `cursor-injection`
originally verified them.

[A trigger message racing a not-yet-processed frame could fire before
the cursor has reached the position the player was actually aiming at]
→ Accepted. The pipeline already reports each processed frame's
position back before the next is accepted (`video-ingest`'s existing
one-report-per-frame contract), so at typical frame rates the gap
between "aim settled" and "trigger sent" is one frame at most, and nothing about this
change makes that gap worse.

[Rapid repeated taps send one trigger message each, with no
debouncing] → Accepted; matches the "physical trigger, physical click"
model, and MAME/emulators already handle rapid clicks as rapid shots.
Nothing here queues or coalesces, so behavior stays predictable.

## Migration Plan

Additive only — no existing endpoint, message, or spec requirement
changes shape. Existing clients that never send a trigger message
continue to work exactly as before; existing servers that receive one
before this change simply ignore it today (unmatched `message.get("type")`)
and will handle it after.

## Open Questions

- ~~Does adding `BTN_LEFT` alongside the existing `BTN_TOUCH` +
  `INPUT_PROP_DIRECT` capabilities preserve direct/touchscreen
  placement, or does it need the two-device fallback?~~ — resolved
  during implementation: it does not preserve it (`udevadm info`
  against a live session showed `ID_INPUT_MOUSE=1` for the combined
  capability set, versus `ID_INPUT_TOUCHSCREEN=1` for `BTN_TOUCH` +
  `INPUT_PROP_DIRECT` alone with no `BTN_LEFT`). `click()` uses the
  two-device fallback; see `tasks.md`'s manual-verification section for
  the recorded findings.
