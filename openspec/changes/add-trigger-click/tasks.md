## 1. Cursor backend click operation

- [x] 1.1 Add `click() -> None` to the `CursorBackend` Protocol in
      `inject.py`
- [x] 1.2 Give `click()` its own `UInput` device carrying only
      `BTN_LEFT` (no `ABS`/`REL` axes), separate from the existing
      `ABS_X`/`ABS_Y` + `BTN_TOUCH` positioning device — adding
      `BTN_LEFT` to the shared device was tried first and found (via
      live-session verification, see §5) to change its udev
      classification from `ID_INPUT_TOUCHSCREEN` to `ID_INPUT_MOUSE`,
      regressing `move_absolute`'s direct placement
- [x] 1.3 Implement `UinputCursorBackend.click()`: `BTN_LEFT` down, syn,
      `BTN_LEFT` up, syn on the click device — no `ABS_X`/`ABS_Y`/
      `BTN_TOUCH` writes, so position is untouched
- [x] 1.4 Implement `FakeCursorBackend.click()`: increment a `clicks`
      counter instead of touching a real device

## 2. Server control-message handling

- [x] 2.1 Thread the cursor backend into `run_frame_session` and
      `_handle_control` (currently closed over `stats` only), sourced
      from `app.state.cursor_backend` the same way `get_cursor_backend`
      already resolves it for `/cursor/move`
- [x] 2.2 Handle `message.get("type") == "trigger"` in
      `_handle_control`: invoke `backend.click()` once per message
- [x] 2.3 Add a `triggers` counter to `SessionStats`, incremented on
      each handled trigger message
- [x] 2.4 Include `triggers` in `SessionStats.as_message`'s payload

## 3. Phone client trigger control

- [x] 3.1 Add a trigger button to `web/index.html`, visually distinct
      from `#start` (this is what the player presses to fire)
- [x] 3.2 Add a "Shots" row to the telemetry panel showing the
      server-acknowledged trigger count
- [x] 3.3 In `capture.js`, wire the trigger button's `pointerdown` (not
      `click`) to send `{"type": "trigger"}` via the existing `send()`
      helper; set `touch-action: none` on the button so touch input
      doesn't first get interpreted as a scroll/zoom gesture
- [x] 3.4 Disable the trigger button until `state.socket` is open;
      re-disable it in `stop()` alongside `#start`'s existing reset
- [x] 3.5 Update the "Shots" stat in `onTelemetry` from the reported
      `triggers` count

## 4. Tests

- [x] 4.1 Test: invoking the cursor backend's click with a fake backend
      records a click, with no `/dev/uinput` access required
      (`tests/test_inject.py`)
- [x] 4.2 Test (websocket, mirroring the existing `rtt` tests in
      `test_stream_e2e.py`): a `{"type": "trigger"}` text message on a
      connected session invokes the fake backend's click once
- [x] 4.3 Test: three trigger messages invoke the fake backend's click
      three times
- [x] 4.4 Test: trigger messages interleaved with frame messages don't
      change frame-processing results (extends the existing malformed
      control-text test's pattern)
- [x] 4.5 Test: the stats message reports a `triggers` count matching
      the number of trigger messages sent so far on the connection
- [x] 4.6 Confirm the full suite still runs via `uv run pytest` with no
      `/dev/uinput` access required (147 passed)

## 5. Manual verification

- [x] 5.1 Live-session check (same method `cursor-injection`'s original
      change used) against this machine's running X11 session
      (`kwin_x11`):
      - Querying `udevadm info --query=property` on a throwaway `UInput`
        device with `ABS_X`/`ABS_Y` + `BTN_TOUCH` + `BTN_LEFT` +
        `INPUT_PROP_DIRECT` showed `ID_INPUT_MOUSE=1` and no
        `ID_INPUT_TOUCHSCREEN` tag at all -- confirming the same
        capability set with `BTN_TOUCH` alone (no `BTN_LEFT`) still
        gets `ID_INPUT_TOUCHSCREEN=1`, so `BTN_LEFT` on the shared
        device is what breaks the classification `move_absolute`
        depends on.
      - Querying the X core pointer's button mask (via `python-xlib`,
        used only as a throwaway diagnostic, never added to the
        project) before/after writes to a `BTN_LEFT`-only device with
        no `ABS`/`REL` capabilities confirmed it delivers a real
        press-then-release to the shared core pointer
        (`Button1Mask`: False -> True -> False) with no motion
        capability at all.
      - Ran the actual `UinputCursorBackend` (two devices, as shipped):
        `move_absolute(0.5, 0.5)` landed pixel-exact at screen center;
        `click()` executed without disturbing position; a further
        `move_absolute` after the click still jumped correctly. No
        regression in direct positioning from adding the click device.
- [x] 5.2 Classification regression confirmed (see 5.1) -- implemented
      the two-device fallback from design.md; re-verified per 5.1
- [ ] 5.3 Run the server, open the client on a phone, start streaming,
      press the trigger, and confirm a left-click lands at the phone's
      current aim point (e.g. observable in a text field's cursor
      placement or a lightgun-aware test target) -- needs a real phone
      and display, not available in this environment
- [ ] 5.4 Confirm the phone's "Shots" counter increments on each press
      -- same hardware dependency as 5.3
