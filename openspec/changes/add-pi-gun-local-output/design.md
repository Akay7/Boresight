# Design

## Context

On a PC, Boresight runs next to a game it does not own. The parts:

- **Overlay.** `boresight.overlay` is a child process that draws tags,
  input-transparent. It uses Qt on X11, and XWayland under a Wayland
  compositor. It reports the geometry it drew.
- **Marker-source controller.** `marker_source.MarkerSourceController`
  starts and supervises the overlay. It derives the solver's layout from
  that report, with the same function the overlay draws with, and hands
  out per-session pipelines, `session_pipeline(cursor)`, with smoothing
  and aim-hold.
- **Cursor.** `inject.UinputCursorBackend` is a Linux absolute pointer.
  Its `/dev/uinput` permission is a udev rule the README already
  documents.

`boresight-gun` (the `usb-hid-gun` spec) runs the same detection and
solve. Its loop, `gun.app.Gun`, sends the aim to a HID gadget. Its only
camera is `hardware.PiCamera`, which uses picamera2. Its
`deploy/pi/install.sh` installs packages with `apt-get`.

Motivation is in proposal.md.

## Goals / Non-Goals

**Goals:**
- The gun installs and runs as Boresight does elsewhere: `uv sync`, then
  `uv run`. No script installs a system package.
- The local output reuses the overlay, controller, cursor and pipeline
  as they are. New code is wiring.
- Cameras need nothing outside pip: a USB webcam via OpenCV, a CSI
  camera via `rpicam-vid`.
- Tags can stay off the game picture on a 16:9 TV, on the server and on
  the gun alike.

**Non-Goals:**
- Running, naming, installing or configuring any game, ROM or emulator.
- The server's web UI on the gun. Zeroing and lens calibration are still
  files copied from a server.
- Drawing over a fullscreen-exclusive window. No overlay can.
- A trigger other than GPIO. A webcam gun on a PC has no trigger yet.

## Decisions

### The local output is the server's own controller and cursor, in the gun

With `output = "local"`, `__main__` builds:
1. a `UinputCursorBackend`
2. a `MarkerSourceController` around it, switched to on-screen markers.
   That starts the overlay with the `[overlay]` settings and waits for
   its geometry, exactly as the server's marker-source route does.
3. `Gun`, with the controller's `session_pipeline(cursor)` in place of
   the pipeline it builds for itself today

So smoothing, aim-hold, the layout, overlay supervision and the
0.01–0.99 edge margin are the server's code paths. Aim behaves the same
with a phone and with the gun.

`Gun` gets one seam: an optional pipeline. It defaults to today's
`AimPipeline` + `HoldingPipeline`, so the USB output is unchanged, and
the existing recorded-frames test pins it. If the controller sees the
overlay exit, the gun stops, and `Gun.run`'s shutdown releases the
button. It exits with a failure, so whatever started it can restart it.

*Alternative:* the full server on the gun, with its camera as a local
client. It would be heavier, with the web stack and a JPEG round trip
per frame, and it is not needed for aiming.

### Cameras: OpenCV for webcams, `rpicam-vid` for CSI, picamera2 kept

A Pi CSI camera sends raw sensor data that the Pi's ISP turns into
images, under libcamera. It never appears as a plain V4L2 capture device.
A USB webcam processes its own images and is plain V4L2, which OpenCV
opens on every OS. So there are two sources, plus the existing one:

- **`webcam`**: `cv2.VideoCapture(device)`, where `device` is an index or
  a path. It asks for the configured size and frame rate, sets manual
  exposure (`CAP_PROP_AUTO_EXPOSURE`, then `CAP_PROP_EXPOSURE` and
  `CAP_PROP_GAIN`) and reads them back.
  - What it gets is logged. If auto exposure is still on, it warns,
    because webcam drivers vary.
  - Frames go to greyscale.
  - There is no sensor timestamp, so the capture-time rule stamps each
    frame at arrival.
- **`rpicam`**: a child process, `rpicam-vid -t 0 -n --codec yuv420 -o -`,
  with `--width/--height/--framerate --shutter <exposure_us> --gain
  <gain> --awbgains 1,1 --denoise off --flush`.
  - Its YUV420 output is the camera buffer written as is, padding
    included. It has no padding when the width is a multiple of 64 and
    the height a multiple of 16, so `rpicam` refuses other sizes at
    startup. 640×480 and 1024×768 qualify.
  - The gun reads exactly `width × height × 3/2` bytes per frame and
    keeps the Y plane.
  - `rpicam-vid`'s standard error is drained into the log, and its last
    lines are reported if it exits.
  - Frames are stamped at arrival.
- **`picamera2`**: today's `PiCamera`, unchanged. It needs the OS's
  `python3-picamera2` and a venv made with `--system-site-packages`.
  It is documented as the option that adds sensor timestamps.

**`auto`**, the default, uses `rpicam` when `shutil.which("rpicam-vid")`
finds it, and `webcam` otherwise. Choosing is one pure function, so it is
tested without either camera.

*Testing:*
- `rpicam` is tested against a stand-in `rpicam-vid`, a small script on
  `PATH` that checks its arguments and writes known frames, and against
  one that dies.
- `webcam` is tested through OpenCV itself, with a video file as the
  device.

### Packaging: extras, and system dependencies left to the user

- **Extras.** `gun` adds `gpiozero` and `lgpio`, which have Arm wheels.
  `local` adds `evdev`, `PySide6-Essentials` and `pydantic`.
  `marker_source` imports `settings`, which uses `pydantic`. On the Pi:
  `uv sync --extra gun --extra local`. That is the same command shape as
  `uv sync --extra overlay` on a PC.
- **What the user installs by hand,** listed in the guide:
  - `uv` and Python 3.12 or newer
  - for `local`: a C compiler and kernel headers, because pip builds
    `evdev`, which has no Arm wheel. Also the uinput udev rule.
  - for `rpicam`: `rpicam-apps`, preinstalled on Raspberry Pi OS
  - for `picamera2`: the OS package, and the venv flag
- **`deploy/pi/install.sh`** stops running `apt-get` and `pip`. It keeps
  the root-only parts of the `usb` output: the dwc2 overlay line, the
  gadget script and the system units. The service's `ExecStart` points
  at the `boresight-gun` in the checkout's `.venv`. The script checks
  that file exists, and if not, says to run `uv sync` first.

### `--autostart`: a desktop autostart entry, for any Linux desktop

`boresight-gun --config X --autostart` writes
`~/.config/autostart/boresight-gun.desktop` with
`Exec=sh -c 'until <this boresight-gun> --config X; do sleep 2; done'`.
That restarts the gun after a failure and stops after a clean exit.
`--autostart remove` deletes the file.

It needs no root, no systemd and nothing distribution-specific: XDG
autostart is what desktop sessions run, Raspberry Pi OS's labwc
included. The path of the program is the one running, so the entry
starts the same venv.

### Side-bar placement in the overlay, for both paths

`overlay.layout.bar_layout` places six tags, 0–3 and 5/7, in the bars
beside a full-height picture of a given aspect, centred on the display.
It and `overlay.render.render_layout` exist already and are tested.

The overlay gets `--picture-aspect W:H`. When it is given, the overlay
draws `render_layout(screen, bar_layout(...))` and includes the aspect in
the geometry it reports, and the controller derives the solver's layout
with the same function. The aspect comes from the server's settings file
(`overlay_picture_aspect`) or the gun's `[overlay] picture_aspect`.
Unset, nothing changes.

The picture is centred on the full display, because an emulator in
windowed full screen covers the panels. The extra margin shrinks the
bars, for an overscanning TV.

### `--emulate` for the local output

`--emulate FRAMES_DIR` with `output = "local"` uses:
- a `FakeCursorBackend`
- a `MarkerSourceController` whose launcher is a stand-in overlay
  process that prints a geometry report for `--screen WxH` (default
  1920×1080) and stays alive

It prints the cursor moves. This runs the real controller, including
deriving the layout from a report, with no display or uinput.

## Risks / Trade-offs

- **The XWayland overlay may not stay above an emulator under a Wayland
  compositor** such as labwc.
  → A hardware task checks it early. The fallback is the overlay's
  wlr-layer-shell path, which needs nothing from the emulator.
- **Webcams honour manual exposure unevenly.**
  → The applied values are read back and logged, with a warning when
  exposure is not fixed.
- **`rpicam-vid`'s raw output and flags could change between versions.**
  → The frame size is checked: a short read is a camera failure, never
  a misaligned frame. A hardware task confirms the flags on the Pi.
- **`evdev` builds on the Pi** in minutes, and needs a compiler.
  → It is documented as a system prerequisite. Raspberry Pi OS ships
  one.
- **Arrival timestamps are a little later than sensor ones.**
  → The smoothing filter only needs consistent intervals. picamera2
  remains available for anyone who wants sensor time.
- **The CPU is shared between the emulator, the overlay and tracking.**
  → Measured in a hardware task. Tracking already drops stale frames.

## Migration Plan

The installed USB setup changes shape:
- **Before:** the program in `/opt/boresight`, from apt and pip.
- **After:** a checkout plus `uv sync --extra gun`, and `install.sh`
  only for the gadget and the service.

The guide says how to remove the old `/opt/boresight`. Configuration
files are unchanged: every new key has a default, and `source = "auto"`
picks `rpicam` on a Pi.

## Open Questions

- Should a webcam gun on a PC take its trigger from a USB button or a
  key? That would be a later change; this one keeps GPIO.
