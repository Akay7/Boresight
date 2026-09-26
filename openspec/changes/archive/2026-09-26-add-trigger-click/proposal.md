## Why

README's own description of the product ends with "a tap on the phone's
on-screen trigger button rides the same connection and is emitted as a
click" — but that button doesn't exist yet. The phone client streams
video and the server solves aim and moves the cursor, but there is no
way for the player to fire. `server.py`'s control-message handler
already has a comment marking the spot ("the trigger event will land
here without disturbing frame handling") and `stream.py`/`video-ingest`
already reserve the WebSocket's text channel for it. This change fills
that gap: it is the last piece needed for the device to work as a light
gun rather than just an aim pointer.

## What Changes

- Add a `click()` operation to the cursor backend interface
  (`inject.py`), implemented on `UinputCursorBackend` as a discrete
  left-button press/release distinct from the existing touch-based
  positioning, and recorded (not emitted) by `FakeCursorBackend` for
  tests.
- Handle a `{"type": "trigger"}` control message on the existing frame
  WebSocket (`server.py`'s `_handle_control`), invoking the cursor
  backend's `click()` and counting it in `SessionStats`/telemetry.
- Add a trigger button to the phone client (`web/index.html`,
  `web/capture.js`) that sends one trigger message per press, enabled
  only while streaming, and reflects the count of shots sent.

## Capabilities

### New Capabilities
- `trigger-emission`: interprets a trigger control message arriving on
  the frame WebSocket as a single click, tying the phone's button to
  the cursor backend's click operation.

### Modified Capabilities
- `cursor-injection`: adds a discrete click operation to the backend
  interface and its Linux `uinput` implementation, alongside the
  existing absolute-move operation.
- `phone-client`: adds an on-screen trigger control that sends a click
  event over the existing connection, and displays how many have been
  sent.

## Impact

- Changed code: `src/boresight/inject.py` (new backend operation),
  `src/boresight/server.py` (control-message handling gains a case,
  `_handle_control` gains access to the cursor backend), `src/boresight/
  stream.py` (`SessionStats` gains a trigger counter), `src/boresight/
  web/index.html` and `web/capture.js` (button, wiring, telemetry
  display).
- No new dependencies, no new endpoints, no wire-format change — the
  trigger message travels on the channel `video-ingest` already reserved
  for control/telemetry text messages.
- Existing cursor-movement behavior (`move_absolute`'s touch-based
  positioning) is unchanged; the click operation is additive to the
  same backend interface.
