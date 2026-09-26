## 1. Shared plumbing

- [x] 1.1 Add `Rect`, `BORESIGHT_CURSOR_RECT` parsing (malformed → `CursorBackendUnavailable` showing `x,y,width,height`) and `default_cursor_backend()` platform dispatch to `inject.py`; verify with unit tests for parsing and for dispatch on `linux`/`win32`/`darwin`/unknown with the platform modules faked
- [x] 1.2 Switch `server.create_app`'s and `pipeline.py`'s default backend to `default_cursor_backend`; verify `tests/test_cursor_move.py` and the full suite still pass

## 2. Windows backend

- [x] 2.1 Add `inject_win32.py` with explicit-width `MOUSEINPUT`/`INPUT` structures and flag constants; verify with a test asserting `sizeof(INPUT)` is 40 (64-bit) / 28 (32-bit) and the field offsets
- [x] 2.2 Implement pixel → virtual-desktop 0..65535 normalisation; verify with an exhaustive round-trip test under Windows' truncating conversion, including negative origins
- [x] 2.3 Implement `Win32CursorBackend` (DPI awareness first, target rect default primary monitor, move/press/release/click/close, relative input before absolute when `BORESIGHT_REL_SCALE` set, one warning when `SendInput` is blocked) over an injectable `Win32Api`; verify with tests against a recording fake API
- [x] 2.4 Implement the real ctypes `Win32Api` (lazy `user32`/`shcore` loading, DPI fallbacks); verify on Windows CI with a test that constructs it and reads the virtual-screen metrics (skipped elsewhere)

## 3. macOS backend

- [x] 3.1 Add `inject_darwin.py` with `CGPoint`/`CGRect` structures and event constants; verify the structure layout in a test
- [x] 3.2 Implement `QuartzCursorBackend` (permission check with request + clear error, target rect default main display, moved vs dragged events, down/up with click state 1, press before any move at the current location, deltas in `kCGMouseEventDeltaX/Y`, close releases) over an injectable `QuartzApi`; verify with tests against a recording fake API
- [x] 3.3 Implement the real ctypes `QuartzApi` (CoreGraphics/CoreFoundation/ApplicationServices loading, `CGPreflightPostEventAccess` with `AXIsProcessTrusted` fallback); verify on macOS CI with a test that constructs it and resolves the main display bounds (skipped elsewhere)

## 4. Portability and CI

- [x] 4.1 Add a test importing `boresight.server`, `boresight.pipeline` and `boresight.marker_source` in a subprocess with evdev, `fcntl` and PySide6 blocked; verify it passes
- [x] 4.2 Add a `windows-latest`/`macos-latest` job to `.github/workflows/ci.yml` running the platform-independent test files; verify the YAML parses and the listed files pass locally
- [x] 4.3 Update README.md (cursor-injection section, platform table, milestone) minimally; verify by reading the rendered sections
- [x] 4.4 Run `uv run ruff check`, `uv run ruff format --check`, `uv run pytest -q` and `openspec validate --all --strict`; verify all pass

## 5. Real hardware (not verifiable here)

- [ ] 5.1 Verify on real Windows: cursor tracks aim on a single monitor at 100% and 150% scaling, and on a secondary monitor via `BORESIGHT_CURSOR_RECT`; trigger clicks and holds (drag) in an emulator (Mesen)
- [ ] 5.2 Verify on real macOS: first start reports the missing Accessibility permission, after granting it the cursor tracks and the trigger clicks and drags on the main display and on a secondary display
- [ ] 5.3 Verify Windows and macOS CI jobs go green on GitHub Actions
