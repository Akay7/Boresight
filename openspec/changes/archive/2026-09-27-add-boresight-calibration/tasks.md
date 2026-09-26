## 1. Correction model and fit

- [x] 1.1 Add `src/boresight/zeroing.py` with `SightFrame` (homography, image size, screen size; image↔screen mapping and local scale in px per screen width) and `Zero` (angular offset as a frame fraction, parallax in screen widths, shots, residual; `aim_mm(frame)`, dict round-trip); verify with unit tests that a zero `Zero` returns the raw aim exactly
- [x] 1.2 Implement `fit(shots)`: per-axis least squares for `(δ, t)` when the shots' scale spans ≥ `PARALLAX_MIN_SPREAD`, mean offset with `t = 0` otherwise, plus the RMS residual; verify with a synthetic pinhole-camera test (tilted and offset barrel, several poses) that the corrected aim at unseen distances lands within a few mm of the barrel's true hit while the raw aim is centimetres off, that two-distance shots recover the parallax offset, and that one-distance shots fit none
- [x] 1.3 Implement targets: inset overlay-area corners + centre + optional repeat when the overlay geometry is known, display corners + optional repeat otherwise; verify by unit test

## 2. Persistence and session flow

- [x] 2.1 Implement `ZeroingStore` over `.boresight/zeroing.json` (atomic write, corrupt file → empty with a warning) and the client-key rule (`id` if `[A-Za-z0-9_-]{1,64}`, else kind, else `unidentified`); verify save/load/delete/corrupt-file tests
- [x] 2.2 Implement the server-wide `ZeroingService` (one run at a time, shows/hides targets through a display callback) and the per-session `SessionZeroing` (identify, start/finish/cancel/reset, shot/miss, auto-finish, close, status dict); verify with unit tests driving the flow with fake frames

## 3. Pipeline integration

- [x] 3.1 `AimPipeline.process_frame(..., zero=None)`: apply the correction before normalization and clamping, attach the frame's `SightFrame` to `FrameResult` (excluded from equality); verify existing pipeline tests pass unchanged and a new test shows a non-zero correction moves the emitted position and debug `cursor_px`
- [x] 3.2 Pass `zero` through `HoldingPipeline` and hold it on `SessionPipeline`; verify a held position is the corrected one
- [x] 3.3 Make `shot.AimHistory` generic so it can hold sight frames; verify `tests/test_shot.py` still passes

## 4. Server wiring

- [x] 4.1 Create the zeroing service in `create_app` (store path overridable for tests), give each session a `SessionZeroing`, identify on `hello` (with the new `id` field) and handle `{"type": "zeroing"}` messages; verify with a socket test that a stored zero is applied after `hello`
- [x] 4.2 Divert trigger presses of a zeroing session in `_SessionTriggers` to the zeroing flow (no claim, no click/press; `up` still releases only a hold that already existed), record each frame's `SightFrame` alongside its aim; verify with a socket test that shots during zeroing never click and advance targets, and that a normal trigger after finishing clicks again
- [x] 4.3 Report `zeroing` in every stats message and end the run on disconnect; verify with socket tests (telemetry fields, a second session refused, disconnect frees the service)

## 5. Overlay target

- [x] 5.1 Add `render.target_image(size_px)` (opaque patch with rings and crosshair) and a pure command parser; verify by unit tests (patch is opaque, centre dark, parser rejects junk)
- [x] 5.2 Add `--commands` to `python -m boresight.overlay`: a stdin reader thread and a Qt timer applying `{"target": [x, y] | null}` to the widget, which paints the target in widget-local coordinates; verify with the offscreen Qt test that the painted target appears where requested and the window still declines input (skipped where PySide6 is absent)
- [x] 5.3 Start the overlay with `--commands` and `stdin=PIPE` in `MarkerSourceController`, add `show_target(position | None)` (normalized, converted to the overlay's pixels) and expose the overlay geometry; verify with a stub overlay that echoes stdin that the target command arrives and that writing to a dead overlay is harmless

## 6. Phone client

- [x] 6.1 Send a persistent random `id` from `localStorage` in `hello`, and dispatch each stats message as a DOM event for other scripts; verify the page serves it (`test_zeroing_server.py`) and `node --check` passes; the in-browser check is part of 7.3
- [x] 6.2 Add `web/zeroing.js` and a zeroing panel in `index.html` (Start/Finish/Cancel/Reset, target prompt, shots, residual), disabled while not streaming; verify the static route test serves `zeroing.js` and `node --check` passes; the on-phone check is part of 7.3

## 7. Docs and checks

- [x] 7.1 Add a short "Zeroing" section to README (how to run it, what the model corrects, when to re-zero, where it is stored); verify by reading
- [x] 7.2 Run `uv run ruff check`, `uv run ruff format --check`, `uv run pytest -q` and `openspec validate --all --strict`; all pass
- [ ] 7.3 Hardware check: zero a real phone-mounted gun on printed markers and on the on-screen overlay, exercising the phone panel (prompts, Done/Cancel/Reset, id kept across reloads), then verify shots land on target from a different distance (requires hardware; not verifiable in CI)
