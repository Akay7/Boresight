## 1. Cursor backend

- [x] 1.1 Add `press()`/`release()` to the `CursorBackend` protocol, `SmoothingCursorBackend` (pass-through) and `FakeCursorBackend` (records presses/releases and whether held); verify with a unit test on the fake
- [x] 1.2 Implement `press()`/`release()` on `UinputCursorBackend` as pen tip down/up with a `_held` flag, make `click()` press+release, and lift a held tip in `close()`; verify in `tests/test_inject_uinput.py` (press/move/release event order, close releases)

## 2. Server

- [x] 2.1 Add a shared `TriggerHold` (per-app set of holding sessions; presses on first holder, releases on last) and unit-test the multi-session rule with the fake backend
- [x] 2.2 Handle `state: down|up` in `_handle_control`, keep plain trigger as click, ignore unknown states, count presses only; verify with e2e tests over the frame WebSocket
- [x] 2.3 Release the session's hold in `run_frame_session`'s teardown; verify with e2e tests for clean disconnect and processor failure
- [x] 2.4 Add the 2 s liveness watchdog; verify a silent holding session is released and a streaming one is not (test with a shortened timeout)

## 3. Phone client

- [x] 3.1 Send `down` on pointerdown (with pointer capture) and `up` on pointerup/pointercancel/lostpointercapture/page hidden/stop, guarded by a `held` flag; suppress long-press menu; verify manually on a phone: long press drags a window, tap still clicks, the shots counter counts presses

## 4. Wrap-up

- [x] 4.1 Document hold/drag in README's trigger section and run the full test suite and `openspec validate add-trigger-hold --strict`
