## Context

`inject.py` defines the `CursorBackend` protocol (`move_absolute`,
`click`, `press`, `release`, optional `close`) and one implementation,
`UinputCursorBackend`, which `server.create_app` uses as its default
factory. Everything above that seam — smoothing, `TriggerHold`, cursor
ownership, trigger timing — is platform-independent and tested through
`FakeCursorBackend`. evdev is already imported lazily inside the uinput
constructor, and the overlay's Qt and Vulkan parts are imported only
when an overlay is started, so the server's import graph has no hard
Linux dependency; nothing, however, checks that it stays that way.

The development and CI machines are Linux. Neither new backend can be
exercised against a real OS here.

## Goals / Non-Goals

**Goals:**
- Windows and macOS backends with the same semantics as uinput: a move
  never clicks, press/release hold the primary button, a click is press
  then release, close releases a held button.
- All platform calls behind a small object per platform, so the
  translation from `CursorBackend` calls to OS events is testable with
  a recording fake on any OS.
- Fail at startup, not on the first frame, when a backend cannot work.

**Non-Goals:**
- A secondary (right) button: the uinput backend has none and no
  client message asks for one.
- A marker overlay on macOS, or verifying the Qt overlay on Windows.
  macOS keeps the existing refusal naming printed markers.
- Verifying on real hardware (left as unticked tasks).

## Decisions

### ctypes, not PyObjC or pywin32
Each backend needs a handful of functions (`SendInput`,
`GetSystemMetrics`, the DPI setters; `CGEventCreateMouseEvent`,
`CGEventPost`, `CGEventSetIntegerValueField`, `CGDisplayBounds`,
`CGPreflightPostEventAccess`, `CFRelease`). `pyobjc-framework-Quartz`
pulls in pyobjc-core and a large compiled framework wrapper; pywin32 is
likewise large. The core install deliberately avoids heavy
dependencies (headless OpenCV, overlay as an extra), and ctypes keeps
the backends importable — and their structures constructible — on
Linux for tests. The cost is declaring the signatures by hand, which
is small and covered by the struct-layout tests.

### A thin platform layer per OS, injected into the backend
`Win32Api` / `QuartzApi` classes own every ctypes call and nothing
else; backends take one as an optional constructor argument. The
backend decides *what* to send (flags, coordinates, event types,
fields); the API object only *sends* it. Tests pass a recorder.
Alternative considered: monkeypatching `ctypes.windll` — not present
on Linux, and it would test ctypes plumbing rather than our logic.

### Windows: explicit-width ctypes fields
`INPUT`/`MOUSEINPUT` are declared with `c_int32`/`c_uint32`/`c_size_t`
rather than `ctypes.wintypes`, whose `LONG`/`DWORD` map to `c_long`,
which is 8 bytes on 64-bit Linux. With explicit widths the structure has
the Windows layout on every host (40 bytes on 64-bit, 28 on 32-bit), so
its size and offsets can be asserted in Linux CI. `SendInput` is given
`sizeof(INPUT)`; a mismatch there is the classic silent failure.

### Windows coordinates: target rect → virtual desktop → 0..65535
The normalised aim maps onto a target rectangle in virtual-desktop
pixels (default: the primary monitor, which always sits at the
origin; override `BORESIGHT_CURSOR_RECT=x,y,w,h`). That pixel is then
normalised over the whole virtual desktop (`SM_XVIRTUALSCREEN` …) and
sent with `ABSOLUTE | VIRTUALDESK | MOVE`. Windows converts back with
`pixel = n * width / 65536` (truncating), so the forward conversion is
the ceiling `ceil(p * 65536 / width)` — the only choice that lands on
exactly `p` for every pixel, which the tests assert exhaustively for
several widths. Negative monitor origins (a monitor left of the
primary) fall out naturally.

The process is made per-monitor DPI aware (`SetProcessDpiAwarenessContext(
PER_MONITOR_AWARE_V2)`, falling back to `SetProcessDpiAwareness(2)` and
then `SetProcessDPIAware()`) before reading metrics, so
`GetSystemMetrics` reports physical pixels on a scaled display. Failure
of all three (or "already set") is not an error.

`SendInput` returning fewer events than given means UIPI blocked them
(the foreground window runs elevated). That is logged once per backend,
not raised: raising mid-session would end the phone's socket over a
condition that goes away when focus changes.

### Windows buttons and relative mode
Press is `LEFTDOWN`, release `LEFTUP`, with no `MOVE` flag, so they act
where the cursor is. With `BORESIGHT_REL_SCALE` set, a move sends a
relative `MOVE` input *before* the absolute one in the same
`SendInput` batch: raw-input readers see the delta, and the absolute
event then puts the OS cursor exactly on target, cancelling any pointer
acceleration applied to the delta.

### macOS: global display points, drag while held
Quartz event locations are in global display coordinates (points,
origin at the top-left of the main display, other displays at their
arranged offsets — negative included). The target rect defaults to
`CGDisplayBounds(CGMainDisplayID())`; `BORESIGHT_CURSOR_RECT` overrides
it in the same space. A move posts `kCGEventMouseMoved`, or
`kCGEventLeftMouseDragged` while the button is held — macOS apps only
see a drag from the latter. Press/release post `LeftMouseDown`/`Up` at
the last position the backend placed (or the current cursor location,
read from `CGEventCreate(NULL)`, before any move), with click state 1.
Relative mode writes the delta into `kCGMouseEventDeltaX/Y` on the move
event, which is what raw-delta readers consume; no second event.

### macOS permission check
Posting events requires the Accessibility (post-event) permission; the
OS silently drops events without it. At construction the backend calls
`CGPreflightPostEventAccess()` (10.15+; `AXIsProcessTrusted()` before
that). If not granted it calls `CGRequestPostEventAccess()` — which
makes the OS show its prompt and list the app in Settings — and raises
`CursorBackendUnavailable` naming System Settings → Privacy & Security →
Accessibility and noting that the permission belongs to the terminal or
Python binary that launched the server, and that a restart is needed.

### Platform selection
`inject.default_cursor_backend()` dispatches on `sys.platform`
(`linux` → uinput, `win32`, `darwin`), importing the platform module
lazily; anything else raises `CursorBackendUnavailable`. `server.py`
and `pipeline.py` use it as their default factory — a one-line change
each, to stay clear of concurrent work in `server.py`.

### Import-safety test and CI
A test imports the server, pipeline and marker-source modules in a
subprocess with evdev, fcntl and PySide6 made unimportable, so a future
top-level import of a Linux-only module fails on Linux CI too. CI gains
a `windows-latest`/`macos-latest` job running a named list of
platform-independent test files, rather than the whole suite: fixtures,
subprocess-based overlay tests and the native builds assume Linux, and
a red cross-platform job for those reasons would hide a real
regression in the backends.

## Risks / Trade-offs

- [ctypes signatures wrong on a real OS] → struct layouts asserted in
  tests; on Windows/macOS CI the real API object is constructed and its
  symbols resolved (no input sent). Real-hardware verification remains
  an unticked task.
- [Exclusive-fullscreen or elevated targets ignore synthetic input] →
  same limitation as uinput, documented; UIPI blocking is logged.
- [Default target is the primary monitor, while uinput maps to the
  whole desktop] → identical on one monitor; on several, the primary
  is the likelier home of the markers, and the rect override covers
  the rest.
- [macOS prompt appears only for the launching binary] → the error
  message says which binary needs the permission.
