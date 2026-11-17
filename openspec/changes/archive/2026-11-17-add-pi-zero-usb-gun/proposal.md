# Proposal

## Why

Every Boresight camera today streams to a PC that does the detection,
solving and cursor injection, so the gun is only usable on a machine
running the server, over Wi-Fi. A Raspberry Pi Zero 2 W has a USB OTG
port that can present itself to any host as a USB mouse, and enough CPU
to run the existing marker pipeline locally. That makes a self-contained
gun: plug it into a PC, a console or an Android box and it aims, with no
software on the host, no Wi-Fi hop and no server.

## What Changes

- Add a standalone gun program, `boresight-gun`, that runs on the Pi:
  capture from a CSI camera, run the existing detection, solve, smoothing
  and aim-hold pipeline in-process, and emit the result as a USB
  absolute-position mouse through the Pi's gadget mode.
- Add a USB HID gadget cursor backend implementing the existing cursor
  backend interface (move, press, release, click), so the pipeline is
  reused unchanged. Coordinates are normalized 0..1 in the pipeline and
  map to the HID absolute range, so the Pi needs no knowledge of the
  host's resolution.
- A physical trigger on a GPIO holds the primary mouse button while
  pressed, like the existing trigger-hold behavior.
- The Pi reads its marker layout, optional lens calibration, optional
  zero and tuning from files; there is no web UI. Files produced by the
  server (lens calibration, zeroing) can be copied onto the Pi.
- Status LED shows searching / aiming / unsolved / error without a screen.
- Provide an installer and systemd unit that configure gadget mode
  (dwc2, configfs HID function) and start the gun at power-up as a
  service; the OTG port is both power and data.
- Provide a mode that runs the same program on any computer with a
  fixture video and a fake HID device, for tests and CI.
- Make the pipeline modules importable without the server's web
  dependencies, so the Pi installs only OpenCV and NumPy.

## Capabilities

### New Capabilities
- `usb-hid-gun`: the self-contained Pi gun -- local aiming from a camera,
  USB absolute-mouse output and trigger, status indication, file-based
  configuration and boot-time service.

### Modified Capabilities
- `packaging`: the aim pipeline must be installable and importable
  without the server's web, TLS and QR dependencies, and the package
  provides a `boresight-gun` command.

## Impact

- New: `src/boresight/gun/` (program, HID backend, GPIO and camera
  adapters, config), `deploy/pi/` (installer, systemd unit, gadget
  setup), tests, a CI step.
- Changed: `pyproject.toml` dependency layout (server deps move behind
  an extra that stays in the default dev sync), README hardware and
  setup sections.
- Server behavior unchanged. The ESP32-CAM and phone paths are unaffected.
- Pi dependencies: `picamera2`, `python3-libgpiod` from apt; NumPy and
  OpenCV from apt or wheels.
