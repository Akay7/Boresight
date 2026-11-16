# The Raspberry Pi gun

A Pi Zero 2 W that aims with its own CSI camera and plugs into a host as a
USB absolute mouse. Nothing runs on the host. See the main README's
"The Raspberry Pi gun" for what it is and is not.

**Never yet run on a Pi.** Everything that can be checked on an ordinary
computer is (`uv run pytest tests/test_gun_*.py`, and `boresight-gun
--emulate FRAMES_DIR`). The checklist at the end lists what only a Pi can
confirm; until it is ticked, treat every default here as a guess.

## What you need

| Part | Notes |
| --- | --- |
| Raspberry Pi Zero 2 W | The only supported board. Others will likely work and are untested |
| Raspberry Pi OS Lite, **Trixie** (64-bit) | The package needs Python 3.12 or later; Bookworm's 3.11 is too old |
| A CSI camera | Camera Module 3 or similar, with the Zero's small camera cable |
| Push button | Between GPIO 17 (header pin 11) and any GND pin. The internal pull-up is used |
| LED and resistor (optional) | GPIO 27 (header pin 13) to the LED, resistor, GND. Without one the state is only logged |
| A USB cable to the host | Into the Pi's **data** port, the one nearer the middle of the board. It also powers the Pi |
| A case (optional) | The printed case in [hardware/case/](../../hardware/case/README.md): the Pi kit with the USB tether drawer. It wires the trigger and LED to the pins above, and its rear cap comes off to reach the micro-SD card |

Set up the SD card with Raspberry Pi Imager: Lite, Trixie, your Wi-Fi and an
SSH user for installing. Wi-Fi is only for you; the gun does not use it.

## Install

On the Pi, from a checkout of this repository:

    sudo deploy/pi/install.sh

It installs the camera and OpenCV packages from apt, the program into
`/opt/boresight`, the USB gadget script and two systemd services, and adds
`dtoverlay=dwc2,dr_mode=peripheral` to `config.txt`. If that line was new,
**reboot once**. After that the Pi enumerates as a mouse whenever it has
power and starts aiming without a login.

## Configure

`/etc/boresight-gun.toml` (copied from `boresight-gun.example.toml`, every
key optional):

- `layout`: your marker layout, in the server's `markers.toml` format. The
  default is the reference layout the test fixtures use — **not** your TV.
  Measure yours as you would for the server and copy the file to
  `/etc/boresight/`.
- `lens_file` / `zero_file`: calibration files the server wrote
  (`.boresight/lenses.json`, `.boresight/zeroing.json`), copied over. Each
  holds one entry per client; name the one to use with `lens_key` /
  `zero_key`, unless the file holds only one. A lens calibration is made at
  one resolution and is refused at any other, and belongs to one physical
  camera: a calibration made for a phone or an ESP32-CAM is wrong for the
  Pi's. Nothing can produce one for the Pi camera yet (the server can only
  calibrate a camera that streams to it), so for now the gun aims without
  lens correction. A Camera Module 3's distortion is mild.
- `[camera]`: resolution, frame rate, and fixed exposure and gain. Exposure
  is never automatic.
- `[pins]`: BCM numbers. Anything that is not a header GPIO, or a trigger and
  LED on the same pin, stops the gun at startup with the pin named.
- `[tuning]`: smoothing, and hold through a dropout, with the server's
  defaults.

Restart after a change: `sudo systemctl restart boresight-gun`.

## Status LED

| Pattern | Meaning |
| --- | --- |
| Short blink, long pause | Starting |
| Slow blink | Running, no frame is solving: the markers are not in view |
| Solid | The latest frame solved |
| Fast blink | An error: read the log |

## Watching it

    journalctl -u boresight-gun -f

Every few seconds it logs the frame rate, the share of frames that solved
and the number dropped. A gun that drops most frames is processing slower
than the camera produces them; lower the resolution.

## The USB side

The device identifies as "Boresight light gun" with the Pi's serial number
(change the names in `/etc/boresight-gadget.conf`: `VENDOR_ID`, `PRODUCT_ID`,
`MANUFACTURER`, `PRODUCT`, `SERIAL`). It reports positions 0–32767 on both
axes, so the host scales them to its display. On a desktop with several
monitors that is the whole desktop.

Unplugging and replugging the cable needs no reboot of the Pi: reports are
dropped while the host is gone and resume when it returns.

The Pi is powered from this same port. A port that cannot supply enough for
the Pi and camera shows up as the Pi restarting under load; use a powered
hub.

## When the host sees nothing

1. `ls /sys/class/udc`: empty means USB device mode is off. Check the
   `dtoverlay` line in `config.txt` and that you rebooted.
2. `systemctl status boresight-gadget`: the failure is printed there.
3. `ls /dev/hidg0` should exist while the gadget is up.
4. Cable in the data port, not the power-only port.

## What only a Pi can confirm

- [ ] Frame rate and solve rate at 640×480 and 1024×768 (the log line)
- [ ] The host enumerates a mouse with no driver; hosts tried: ______
- [ ] Aim lands where it should, on a host with one display
- [ ] Unplug and replug the cable without a reboot
- [ ] A power cycle ends with a working gun and no login
- [ ] Default exposure and gain are sensible for the camera in use
