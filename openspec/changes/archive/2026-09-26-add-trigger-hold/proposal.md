## Why

The trigger is a one-shot click: the phone sends one message on press,
the ESP32 drops releases, and the server taps the button down and up at
once. Nothing can be held, so dragging (moving a window, a slider, a
drag-to-aim game, holding fire) is impossible, even though the cursor
already follows the aim continuously.

## What Changes

- The trigger message gains an optional `state`: `{"type": "trigger",
  "state": "down"}` presses and holds the primary button,
  `{"type": "trigger", "state": "up"}` releases it. Aim movement while
  it is held is a drag. A plain `{"type": "trigger"}` still means one
  click, so older clients (including already-flashed ESP32s) keep
  working unchanged.
- The cursor backend gains `press()` and `release()` alongside
  `click()`, implemented on the uinput pen as tip-down and tip-up.
- The server never leaves the button stuck: a held button is released
  when its session ends for any reason, and when the holding session
  goes silent (no frame or message) for longer than a short liveness
  window.
- The phone client sends `down` on press and `up` on release, and also
  `up` when the pointer is cancelled or lost, the page is hidden, or
  streaming stops.
- The ESP32 firmware's matching press/release behaviour is specified
  and tracked in `add-esp32-cam-firmware`.
- Trigger telemetry counts presses (`down` and plain clicks), so the
  shots counter keeps its meaning.

## Capabilities

### New Capabilities
- `trigger-hold`: the press/release trigger protocol, how the server
  maps it onto a held button, and the rules that guarantee the button
  is released.

### Modified Capabilities
- `cursor-injection`: the backend can hold and release the primary
  button, not only click it.
- `phone-client`: the on-screen trigger sends press and release rather
  than one click per press.
- `video-ingest`: disconnection also releases a button the session was
  holding.

## Impact

- `src/boresight/inject.py`: `CursorBackend` protocol, uinput pen,
  smoothing wrapper, fake backend.
- `src/boresight/server.py`: `_handle_control`, session teardown, hold
  liveness watchdog.
- `src/boresight/web/capture.js`: trigger pointer handling.
- Tests: `tests/test_stream_e2e.py`, `tests/test_inject.py`,
  `tests/test_inject_uinput.py`.
- Wire compatibility: additive. A plain `{"type": "trigger"}` behaves
  exactly as before.
