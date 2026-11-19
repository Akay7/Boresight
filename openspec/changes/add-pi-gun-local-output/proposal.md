# Proposal

## Why

The Pi Zero 2 W gun only works as a USB mouse for another machine that
runs the game. On a PC, Boresight already runs next to a game it does
not own:
- the overlay draws the markers over the game
- the uinput pointer moves the cursor the game reads as a light gun
- the pipeline aims from camera frames

A Pi with an HDMI port and a desktop can run any emulator, and the gun
only has to run those same pieces, with its own camera as the frame
source. The gun plugged into a TV is then the whole setup, and
Boresight works the same way on the Pi as on any other system.

That also means installing it the same way everywhere. Today the gun
needs a Pi-only script that calls `apt-get`, and it can only read a Pi
CSI camera through a Python binding that pip cannot install.

## What Changes

- **Output setting.** `boresight-gun` gets `output`, either `usb` or
  `local`. `usb` is today's HID gadget and stays the default. `local`
  aims at the display the gun's computer drives:
  - the existing uinput absolute pointer is the cursor
  - the existing overlay draws the markers, supervised by the existing
    marker-source controller, so the drawn and solved layouts are one
    layout
  - the GPIO trigger holds the primary button
- **Side bars.** The overlay gains a side-bar placement. A 4:3 or 8:7
  picture on a 16:9 TV leaves bars at the sides. With a picture aspect
  set, the tags go in those bars and never over the game, on the server
  and on the gun alike.
- **Cameras.** The gun reads either a USB webcam, through OpenCV on any
  system, or a Pi CSI camera, through the `rpicam-vid` program Raspberry
  Pi OS ships. Neither needs a Python binding outside pip. `auto`, the
  default, picks the CSI camera where `rpicam-vid` exists, and the
  webcam otherwise. The picamera2 camera stays as an explicit choice.
- **Install.** The gun installs like Boresight on any system: clone,
  `uv sync` with its extras, `uv run boresight-gun`. No script installs
  a system package. The docs list every system dependency for the user
  to install by hand.
- **Starting on login.** `boresight-gun --autostart` writes a desktop
  autostart entry for the current user, which restarts the gun if it
  fails. It needs no root and works on any Linux desktop.
- **Root setup only for USB.** The Pi script keeps only what the `usb`
  output needs root for: the USB gadget and the boot service. It
  installs no packages.
- **Hand checks.** The USB gun's open hand checks on a Pi carry over
  here. They were moved out of `add-pi-zero-usb-gun` when it was
  archived.

## Capabilities

### New Capabilities
- `pi-gun-local-output`: the gun aiming at its own display. Covers
  choosing the output, the local cursor and trigger, the markers through
  the existing overlay with one layout, the autostart entry, and running
  without a Pi.

### Modified Capabilities
- `usb-hid-gun`:
  - The USB mouse and its gadget become the `usb` output, which is the
    default and otherwise unchanged.
  - The camera can be a USB webcam or a CSI camera through
    `rpicam-vid`.
  - Installation uses the project's normal Python packaging, with
    system dependencies documented and installed by the user.
- `marker-overlay`: adds the side-bar placement beside a centred picture
  of a given aspect.

## Impact

- **Code.**
  - `boresight.gun`:
    - config: `output`, `[overlay]`, `[camera] source` and `device`
    - camera sources: `rpicam-vid` and OpenCV
    - the local output, wired from `inject.UinputCursorBackend` and
      `marker_source.MarkerSourceController`
    - `--autostart`, and `--emulate` for the local output
  - `boresight.overlay`: the side-bar placement (`layout.bar_layout` and
    `render.render_layout`, already written) and a CLI option for it.
  - `marker_source` and the settings file: a picture-aspect setting.
  - `pyproject.toml`: a `gun` extra (`gpiozero`, `lgpio`) and a `local`
    extra (`evdev`, `PySide6-Essentials`, `pydantic`).
  - `deploy/pi`: the script stops installing packages and keeps only the
    gadget and boot service.
- **System dependencies, installed by the user and documented.**
  - `uv` and Python 3.12 or newer
  - for `local`: a C compiler and kernel headers, because pip builds
    `evdev`, which has no Arm wheel. Also the uinput udev rule the
    server already documents.
  - for the CSI camera: `rpicam-apps`, which Raspberry Pi OS preinstalls
  - for the picamera2 camera only: the OS's `python3-picamera2`, and a
    venv made with `--system-site-packages`
- **Unchanged:** the server's behaviour (the new placement is opt-in),
  the USB output's behaviour, and the ESP32-CAM and phone paths.
- **Not done:** Boresight never runs, ships, names or configures a game,
  a ROM or an emulator.
