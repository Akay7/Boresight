# Tasks

## 1. Packaging

- [x] 1.1 Move `fastapi`, `uvicorn`, `evdev`, `cryptography`, `segno` to a `server` extra and include it in the `dev` group; verify `uv sync` + `uv run pytest` are unchanged
- [x] 1.2 Make the `boresight` command print an actionable message when the `server` extra is missing; verify by running it in a core-only venv
- [x] 1.3 Add a test/CI step that installs core-only in a clean venv and imports `boresight.pipeline`, `boresight.aim_hold`, `boresight.lens`, `boresight.zeroing`; verify it passes in CI
- [x] 1.4 Add the `boresight-gun` script entry (`python -m boresight.gun`); verify `boresight-gun --help` equals the module form

## 2. HID backend

- [x] 2.1 Define the report descriptor in one place and implement `HidGadgetBackend` (absolute 16-bit X/Y, one button, press/release/click, clamp 0..1); verify with unit tests that parse reports against the descriptor, including that a press does not move the cursor
- [x] 2.2 Handle suspended/unplugged hosts (`EAGAIN`/`ESHUTDOWN`) without stalling, reopen after replug, count and log drops; verify with a fake device that raises those errors
- [x] 2.3 Release a held button on shutdown and camera failure; verify with a unit test

## 3. Gun program

- [x] 3.1 Add `boresight.gun` config loading (TOML; layout, lens, zero, camera, pins, USB strings, tuning with server defaults) and reject invalid files at startup; verify with unit tests for defaults, overrides and each failure
- [x] 3.2 Implement the capture/aim loop with a one-frame slot, frame dropping with counters, capture-time rule, `AimPipeline`+`HoldingPipeline` wiring and periodic fps/solve/dropped log; verify with a slow-detector test that lag does not grow
- [x] 3.3 Implement pin validation, the debouncer and trigger→press/release wiring; verify with unit tests for bounce, duplicate pin and reserved pin
- [x] 3.4 Implement the LED patterns and no-LED mode; verify the aiming→searching switch with a unit test
- [x] 3.5 Implement `--emulate`: fixture frame source, injected button levels, recording HID sink; verify the reports equal `boresight.pipeline.replay` for the same frames and an injected press gives one down and one up
- [x] 3.6 Add the emulated run to the test suite and CI; verify `uv run pytest` and `ruff check`/`ruff format --check` pass

## 4. Pi hardware adapters

Code written: picamera2 camera and gpiozero trigger/LED in
`src/boresight/gun/hardware.py`. Hand checks on a Pi moved to
`add-pi-zero-nes-console`, group 7.

## 5. Deployment

Written: `deploy/pi/boresight-gadget.sh` (shellcheck clean), systemd units
and `install.sh`. Hand checks on a Pi (enumeration, power cycle, replug)
moved to `add-pi-zero-nes-console`, group 7.

## 6. Documentation

`deploy/pi/README.md` written; following it on a fresh SD card moved to
`add-pi-zero-nes-console`, group 7.

- [x] 6.2 Update the main README: hardware table, install line for the `server` extra, a Pi section beside the ESP32-CAM; verify links resolve
- [x] 6.3 Run `openspec validate add-pi-zero-usb-gun --strict`; verify it passes
