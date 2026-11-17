# Design

## Context

The aim pipeline is already server-independent: `AimPipeline` and
`HoldingPipeline` take an `np.ndarray` frame and a `CursorBackend`
(`move_absolute`, `press`, `release`, `click`, normalized 0..1), and the
modules they use (`detect`, `solve`, `marker_map`, `lens`, `zeroing`,
`one_euro`, `aim_hold`) import none of the web stack. `inject.py` imports
`evdev` only inside the uinput backend. So the Pi gun is a new front end
and a new backend around existing code. See proposal.md for motivation.

The Pi Zero 2 W: quad Cortex-A53, 512 MB, CSI port, and a micro-USB OTG
port that Linux can run as a USB device (dwc2 + configfs gadget).

## Goals / Non-Goals

**Goals:**
- Reuse the pipeline unchanged; identical aim for identical frames.
- Plug-and-play on any host that takes a USB mouse.
- Everything except the camera, GPIO and USB device nodes testable on a PC.

**Non-Goals:**
- No web UI, settings API, recording, overlay or zeroing-by-shooting on the
  Pi. Lens calibration and zero files are produced on the server and copied
  over; tooling to generate them on the Pi is a later change.
- No Wi-Fi/streaming mode (the camera-only Pi client is a separate idea).
- No composite devices (keyboard, gamepad) or relative-mouse mode.
- Pi models other than Zero 2 W, and USB cameras, are unsupported.

## Decisions

**Same package, new subpackage `boresight.gun`; Pi installs it directly.**
Keeps one copy of the pipeline. *Alternative:* a separate project that
vendors the modules -- would drift. Needs the dependency split below.

**Split dependencies, keep the default sync.** Core dependencies become
`numpy` and `opencv-python-headless`; `fastapi`, `uvicorn`, `evdev`,
`cryptography`, `segno` move to a `server` extra, and the `dev` group
includes it, so `uv sync` and CI see no change. On the Pi, install
`pip install .` (no extras) with `python3-opencv`/`numpy` from apt if
wheels are slow. *Risk:* `pip install boresight` for server users now
needs `[server]` -- the `boresight` command must print an actionable
message when the extra is missing, and the README install line changes.

**`HidGadgetBackend` writes 5-byte reports to `/dev/hidg0`.** Report
descriptor: one button (plus padding), X and Y absolute 16-bit 0..32767.
Positions are scaled `round(x * 32767)` after clamping to 0..1. Press,
release and click each send a full report carrying the last position, so
a press never moves the cursor. Writes are non-blocking; a host that has
suspended or is unplugged raises `EAGAIN`/`ESHUTDOWN`, which the backend
swallows while it counts and logs, so the capture loop never stalls.
*Alternative:* relative mouse -- loses the absolute aim that defines the
gun. *Alternative:* digitizer/touch descriptor -- some hosts treat it as
touch and hide the pointer; a plain absolute mouse is the broadest match.
Hosts that scale an absolute mouse to a multi-monitor desktop will aim
across all monitors; documented, as the server's display choice isn't
available here.

**Gadget setup in a shell script, not in Python.** `deploy/pi/` has
`boresight-gadget.sh` (configfs: vendor/product/serial/strings, one HID
function, bind to the UDC) run by a oneshot unit before the gun, plus
`install.sh` that adds `dtoverlay=dwc2` and `modules-load=dwc2` and
tells the user to reboot once. The script is idempotent and unbinds on
stop. The gun opens `/dev/hidg0` and, on `ESHUTDOWN` after replug,
reopens it. The descriptor lives in one place that both the script and
the tests read, so a test can check the backend's reports against the
descriptor it declares.

**Capture: picamera2 raw luma, no JPEG.** Request the `YUV420`/`Y`
plane at the configured size (default 640x480 -- the detector needs
about 25 px per marker, so 1024x768 is a config option once measured) and
hand the array to the pipeline directly. Skipping JPEG removes an
encode and a decode per frame. A capture thread keeps a one-frame slot;
the aim thread takes the newest, so a slow solve drops frames rather than
queues them. Exposure and gain fixed through controls (`AeEnable=False`,
`ExposureTime`, `AnalogueGain`), AWB off.

**Time base.** The aim filter wants capture time in seconds; use the
sensor timestamp from the frame metadata when plausible, else the grab
time (the same rule the ESP32 firmware uses).

**Hardware behind `Camera`, `Trigger`, `Led`, `Sink` seams with fakes.**
`--emulate VIDEO` reads frames from a fixture sequence, injected button
levels, and a recording sink in place of `/dev/hidg0`; `boresight.pipeline.replay`
semantics make the expected reports computable. CI runs this and the
test compares against server replay. Real implementations are thin and
checked by hand on a Pi.

**GPIO via gpiozero (lgpio backend), BCM numbering,** default trigger
GPIO 17 and LED GPIO 27. The button is polled every 2 ms by the trigger
thread and fed to a pure debouncer, rather than using edge callbacks, so
the debounce rule is the tested code. libgpiod's Python bindings were the
first choice but Raspberry Pi OS Bookworm ships the incompatible 1.x API;
gpiozero+lgpio is in both. Allowlist: header GPIOs 2-27.

**Files, not UI.** One TOML config (`/etc/boresight-gun.toml`):
`layout` path (the server's `markers.toml` format), optional `lens` and
`zero` paths in the server's JSON formats, camera, pins, USB strings,
smoothing/hold tuning with the server's defaults. The shipped
`markers.toml` is the default layout; users with another display edit
it as they do for the server today.

**Service runs as root.** Writing configfs and `/dev/hidg0` need it;
a dedicated user with udev rules is possible later. The unit uses
`ProtectSystem=strict`, `ProtectHome`, `NoNewPrivileges` and `PrivateTmp`.
A `DeviceAllow` list was left out: the camera stack opens a long,
version-dependent list of nodes and a wrong list breaks the camera.

**Raspberry Pi OS Trixie.** The package requires Python 3.12; Bookworm
has 3.11.

## Risks / Trade-offs

- Pipeline speed on a Cortex-A53 is unmeasured; the tracker avoids full
  searches but a 1024x768 full pass may be slow. → Default to 640x480,
  measure fps with the solve-rate log line, record results in the README;
  frame dropping keeps latency bounded either way.
- USB power: the OTG port both powers the Pi and carries data; a console
  port may supply too little for the camera. → Document a powered Y-cable
  or hub, and the brown-out symptom.
- Boot time (~20-30 s) before the mouse enumerates. → Documented; a
  trimmed image is future work.
- Absolute-mouse hosts: some consoles and Android versions ignore or
  mis-scale absolute mice. → State which hosts were tested; this is the
  main compatibility risk and can't be solved in software here.
- No lens/zero tooling on the Pi means uncalibrated aim until files are
  copied. → Document the copy workflow; pipeline works without them.
- Splitting dependencies could break `pip install boresight` for
  existing server users. → Actionable error message, README update, CI
  job that imports the pipeline in a minimal environment.

## Migration Plan

Additive for users of the server, except the install extra noted above.
Pi users run the installer and reboot once. Rollback: remove
`src/boresight/gun/`, `deploy/pi/` and revert the dependency layout.

## Open Questions

- Whether to also expose a keyboard or gamepad interface later; the
  gadget script allows more functions, nothing here depends on it.
