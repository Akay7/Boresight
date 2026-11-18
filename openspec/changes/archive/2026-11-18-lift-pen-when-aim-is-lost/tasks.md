# Tasks

## 1. Cursor backend

- [x] 1.1 Add `idle()` to `CursorBackend`, the smoothing wrappers and `FakeCursorBackend` (counted in `idles`), and as a no-op on Windows, macOS and the HID gun; verify `uv run pytest` passes
- [x] 1.2 Uinput pen: start out of proximity, enter with the first move's position in the same frame, make one real proximity out on the first entry, leave on `idle()` unless the tip is held, and put the tip down only while hovering; verify with fake-device tests for each, including close
- [x] 1.3 Confirm the libinput behaviour against the 1.32.0 source (`src/libinput-plugin-tablet-proximity-timer.c`: `FORCED_PROXOUT_TIMEOUT` 50 ms, applied to every tablet-tool device, unloaded on the first real `BTN_TOOL_PEN 0`)

## 2. Who stops the aim

- [x] 2.1 `HoldingPipeline` calls `idle()` on each unsolved frame past the window, or on every unsolved frame with holding off; verify with unit tests
- [x] 2.2 The cursor gate passes `idle()` on only for the owner or a free cursor, and calls it when the owner's session closes; verify with unit tests and an end-to-end disconnect test through the server

## 3. Docs and hardware

- [x] 3.1 README: the Linux pen in "Cursor injection", and the libinput timer in "Holding through a brief dropout"
- [x] 3.2 On the bench (ESP32-CAM, KDE Plasma Wayland): the cursor holds steady without blinking while aiming, disappears once the aim is lost, and VS Code takes mouse clicks after the aim has left it
      (Confirmed by the user on 2026-11-17 with the ESP32-CAM at ~12 fps, KDE Plasma 6.8, libinput 1.32.)
