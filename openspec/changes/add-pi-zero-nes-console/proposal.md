# Proposal

## Why

The Pi Zero 2 W gun (`add-pi-zero-usb-gun`) still needs a host to play
on: a PC, a console or an Android box that runs the game and takes the
gun as a USB mouse. The same Pi already has a mini-HDMI port, four cores
and a camera. If it also ran the game, the gun alone, plugged into a TV
over HDMI, would be the whole light-gun console. Nothing else would be
needed, not even a host for the markers, because the Pi would draw them
on the TV itself.

The Pi can carry this load. NES emulation needs a fraction of one
Cortex-A53 core. Scaling a 256×240 picture is GPU work. That leaves most
of the CPU for marker tracking, which already drops stale frames rather
than falling behind (see design.md, "Budget").

## What Changes

- A **console mode** for `boresight-gun`. The Pi runs a NES emulator,
  shows the game full screen on its HDMI output, and plays the game's
  sound over HDMI. The camera tracking runs in the same program.
- The TV is wider than the NES picture, so the game sits centred with
  bars at the sides. The program draws the **markers in those bars**,
  never over the game. The tag positions come from the same single
  layout computation the solver uses, so the drawn and solved positions
  cannot differ.
- The aim and trigger drive the **emulated NES Zapper** directly: the
  aim point maps to a pixel in the game picture, and the trigger is the
  Zapper trigger. There is no mouse in between. Aiming at the bars or
  off the TV counts as shooting off-screen, as games like Duck Hunt
  expect.
- **Start** and **Select** come from two optional extra GPIO buttons on
  the gun. An optional USB gamepad on the Pi's USB port acts as
  controller 1. Many Zapper games need Start or Select to begin.
- The game runs from **ROM files the user supplies**. None are shipped.
  The config names a ROM, or a folder of ROMs that the gun cycles
  through with Select held at power-up. With no ROM the screen shows the
  markers and a message, so aiming can still be checked.
- The mode is chosen in `boresight-gun.toml`: `usb` (today's mouse) or
  `console`. One install supports both. Console mode does not configure
  the USB gadget, which frees the port for the gamepad.
- The gun logs **under-voltage and thermal throttling**, which are the
  usual failures of a Pi Zero 2 W running at full load from a weak
  supply.
- `--emulate` also covers console mode. It uses a stand-in emulator core
  and an off-screen display, so the tests and CI exercise the mapping
  from aim point to Zapper and from layout to drawn picture without a
  Pi, a TV or a ROM.

## Capabilities

### New Capabilities
- `gun-console`: the Pi gun as a self-contained console. Covers running
  a NES game on its HDMI output with sound, drawing the markers beside
  the game picture from the solver's layout, driving the emulated Zapper
  from the aim and trigger, the Start/Select and gamepad inputs, ROM
  selection, choosing between console and USB mode, power and thermal
  reporting, and running without a Pi.

### Modified Capabilities
- None. `usb-hid-gun`'s behaviour does not change: USB mode stays the
  default. That change was archived before its hand checks on a Pi; those
  checks moved here (tasks group 7), because console mode needs the same
  camera, buttons and install working first.

## Impact

- New: `src/boresight/gun/console/`, holding the libretro frontend,
  the display and audio output, the console layout, the Zapper mapping
  and a stand-in core for tests. Also new tests and a CI step for the
  emulated console.
- Changed:
  - `boresight.gun` config: `mode`, `[console]` (ROM path, scaling),
    and Start/Select pins in `[pins]`.
  - `__main__` chooses the output by mode.
  - `boresight.overlay.layout` gains a placement for tags in side bars,
    or a sibling function next to it. The existing full-screen
    placement is unchanged.
  - `deploy/pi/install.sh` installs the NES core and SDL2 from apt. The
    systemd unit starts the gadget only in USB mode.
  - `deploy/pi/README.md` gains a console section covering the HDMI
    cable, power supply, heatsink and buttons.
- New Pi dependencies, from apt: `libretro-nestopia` (the NES core) and
  SDL2 with its Python binding.
- Hardware: a 5 V 2.5 A supply into the Pi's power port, since a TV's
  USB port is usually too weak. A heatsink on the SoC. A mini-HDMI to
  HDMI cable from gun to TV. Two optional buttons.
- The server, the ESP32-CAM and phone paths, and USB mode are unaffected.
- No ROMs or other copyrighted game data in the repository or packages.
