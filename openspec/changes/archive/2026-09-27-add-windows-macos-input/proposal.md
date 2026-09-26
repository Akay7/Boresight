## Why

The only cursor backend is Linux uinput, so the server cannot drive the
cursor anywhere else and refuses to be useful on Windows or macOS —
where most emulators and light-gun games are actually played. Both
platforms have a documented, dependency-free way to synthesise absolute
pointer input (`SendInput`, Quartz `CGEvent`), reachable from the
standard library's `ctypes`.

## What Changes

- Add a Windows cursor backend over `SendInput`: absolute moves in
  virtual-desktop coordinates (`MOUSEEVENTF_ABSOLUTE |
  MOUSEEVENTF_VIRTUALDESK`, normalised 0..65535), left button down/up for
  click and hold, optional relative deltas under the existing
  `BORESIGHT_REL_SCALE`, and per-monitor DPI awareness so screen
  geometry is read in physical pixels.
- Add a macOS cursor backend over Quartz `CGEvent` (via `ctypes`, no
  PyObjC): absolute moves in global display coordinates, left button
  down/up, drag events while held, optional relative deltas, and an
  up-front check for the permission macOS requires to post events, with
  a message saying exactly where to grant it.
- Select the backend by platform, keeping the `CursorBackend` interface
  and `CursorBackendUnavailable` error unchanged. An unsupported platform
  fails at startup with a clear message.
- Let the cursor be mapped onto one monitor of a multi-monitor desktop
  (`BORESIGHT_CURSOR_RECT`), defaulting to the primary display.
- Keep every OS call behind a thin injectable layer, so the event
  construction (struct layouts, coordinate normalisation, button
  sequences) is unit-tested on Linux with fakes.
- Guarantee the server imports and starts without Linux-only modules
  (evdev, the Qt/Vulkan overlay parts), and add Windows and macOS jobs to
  CI running the platform-independent tests.
- README: platform table and cursor-injection section updated.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `cursor-injection`: absolute positioning, click and hold are defined
  for Windows and macOS as well as Linux; the backend is chosen by
  platform; startup fails fast on a missing macOS permission or an
  unsupported platform; the target display area is configurable.
- `packaging`: the server starts on Windows and macOS without Linux-only
  modules, and the test suite's platform-independent part runs there.

## Impact

- New `src/boresight/inject_win32.py`, `src/boresight/inject_darwin.py`;
  `src/boresight/inject.py` gains platform selection and display-rect
  parsing.
- `src/boresight/server.py` and `src/boresight/pipeline.py`: default
  backend factory switches from `UinputCursorBackend` to the platform
  selector (one line each).
- `.github/workflows/ci.yml`: Windows and macOS test jobs.
- No new dependencies. The marker overlay is unchanged: it already
  refuses to start on macOS and names printed markers instead.
