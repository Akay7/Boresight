## Context

The trigger currently travels as `{"type": "trigger"}` on the frame
WebSocket. `_handle_control` calls `backend.click()`, which on uinput is
a pen tap: `BTN_TOUCH` plus `ABS_PRESSURE` down, then up, on the
`boresight-cursor` pen device. It used to be `BTN_LEFT` on the separate
relative device, which on KWin/Wayland clicked at a different pointer
from the one the pen moves. Every session shares one backend,
`app.state.cursor_backend`, wrapped per marker source in
`SmoothingCursorBackend`. The server's `click()` call uses the
unwrapped backend.

Senders: `capture.js` sends on `pointerdown` only, and the ESP32's
debouncer (`bp_debounce_update`) reports only `BP_BUTTON_PRESSED`.

## Goals / Non-Goals

**Goals:**
- Press and release as separate events end to end, with drag coming
  from the existing per-frame `move_absolute`.
- No way to leave the button stuck down short of the server process
  itself hanging.
- Old clients keep their exact behaviour.

**Non-Goals:**
- Right or middle button, or more than one button.
- Any change to the relative-motion device or `BORESIGHT_REL_SCALE`.
- Extra smoothing during a drag. Drag precision is whatever aim
  precision already is.

## Decisions

### `state` on the existing message, not new message types
`{"type": "trigger", "state": "down"|"up"}`. The server already ignores
fields it does not read, and a missing `state` keeps the old meaning, so
the change is purely additive. Separate `press`/`release` types would
work just as well, but would split one concept across three names.

### The pen tip is the held button
`press()` writes `ABS_PRESSURE=CLICK_PRESSURE` and `BTN_TOUCH=1`, then
a sync. `release()` writes both back to 0, then a sync. `click()` is
`press()` then `release()`. `move_absolute` touches only `ABS_X`/`ABS_Y`,
so a tip that is down stays down across moves, which libinput and the
compositor deliver as a drag. This keeps the hold on the same pointer
the cursor moves, which is the fix for the Wayland click bug.
The backend tracks `_held` so a `close()` with the tip down lifts it
before leaving proximity.

`SmoothingCursorBackend` and `FakeCursorBackend` gain pass-through or
recording `press`/`release`. The `CursorBackend` protocol gains both.

### Hold ownership lives in the server, not the backend
A shared `TriggerHold` object (one per app, on `app.state`) holds the
set of sessions currently holding. `acquire(session)` presses the
backend when the set goes from empty to non-empty, and `release(session)`
lifts the button when it goes back to empty. Both are idempotent per
session. The backend stays a dumb device, and the multi-session rule
("released when the last holder lets go") is one small piece of code
that is easy to test with the fake backend.

Alternative: a reference count in the backend. Rejected, because the
backend cannot know which session a call belongs to, so a session's
teardown could not undo only its own hold.

### Release on every way a session can end
`run_frame_session`'s `finally` calls `hold.release(session)`. That
single place covers a clean close, an abrupt drop, a processor failure
(1011 close) and cancellation.

### Liveness watchdog rather than a maximum hold time
A max-duration cap would break legitimate long holds, such as holding
fire. Instead, the session records `last_message_at` on every received
message, frame or text. A small task started with the session checks
every 0.5 s and, if the session holds and more than
`HOLD_IDLE_RELEASE_S = 2.0` has passed, releases the hold and logs it
once. Both clients stream frames many times a second while they are
active, so 2 s of silence means the client is stalled: a backgrounded
tab, a hung ESP32, or a half-open socket that pings have not caught yet.
The ESP32's websocket ping timeout is 10 s, so without the watchdog a
dead link could hold for that long.

### Telemetry counts presses
`stats.triggers` increments on a plain click and on a `down` that
actually starts this session's hold. The phone's "shots" counter keeps
meaning shots.

### Phone: pointer capture and a local `held` flag
On `pointerdown`: `setPointerCapture`, then send `down`, then set
`held`. On `pointerup`, `pointercancel` and `lostpointercapture`, a
`releaseTrigger()` helper sends `up` if `held` is set and clears it. The
same helper runs on `visibilitychange` to hidden and at the start of
`stop()`, before the socket is closed. The `#trigger` style adds
`-webkit-touch-callout: none` and the element gets a `contextmenu`
`preventDefault`, so a long press does not open a menu.

### ESP32
The firmware side (debouncer release events, `down`/`up` messages, and
sending `up` only on the connection that carried the `down`) is in
`add-esp32-cam-firmware`, alongside the rest of the device's
requirements.

## Risks / Trade-offs

- [A client's `up` is lost on the wire] → The watchdog cannot catch this
  while frames keep flowing, so the button stays down until the player
  presses and releases again, or disconnects. Mitigation: the phone's
  `up` path has several triggers, and WebSocket/TCP delivery is
  reliable once connected. The only realistic loss is a disconnect,
  which the teardown release covers.
- [Aim jitter makes drags imprecise] → Accepted and documented. Smoothing
  already applies to movement during a hold.
- [Tip down in a tablet-aware app behaves as a pen stroke, e.g. draws in
  Krita] → That is what a held primary button means in those apps, the
  same as the click that already works this way.
- [A 2 s stall is also possible on a very slow link] → The hold
  releases, and the next press starts a new one. Frames are dropped
  newest-first but still arrive, so a link slower than 0.5 fps is
  already unusable for aiming anyway.

## Migration Plan

Additive on the wire. Deploy the server first. Old phone pages and old
ESP32 firmware keep sending plain triggers and keep clicking. Reload the
phone page and reflash the ESP32 to get hold. An old server ignores
`state`, so it would click on both `down` and `up`, turning every tap
into a double-click. After rolling the server back, roll back or reload
the clients too.
