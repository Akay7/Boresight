# The Raspberry Pi gun

A Pi Zero 2 W that aims with its own camera. It has two outputs:

- **`usb`** (the default): it plugs into a host as a USB absolute mouse.
  Nothing runs on the host.
- **`local`**: it aims at the display it drives itself, for example a TV
  on its HDMI port, while any emulator or game runs on its desktop. See
  "Next to an emulator" below.

See the main README's "The Raspberry Pi gun" for what it is and is not.

The gun installs like the rest of Boresight, with `uv sync`. No script here
installs a system package. The few things the system has to provide are
listed under "System dependencies", for you to install with your system's
own package manager.

**Never yet run on a Pi.** Everything that can be checked on an ordinary
computer is (`uv run pytest tests/test_gun_*.py`, and `boresight-gun
--emulate FRAMES_DIR`). The checklist at the end lists what only a Pi can
confirm; until it is ticked, treat every default here as a guess.

## Quick start

Two paths from a blank SD card to a working gun. Pick one:

- **A** if the Pi drives a TV and an emulator runs on it, or
- **B** if the Pi is a USB mouse for another machine.

Every step ends with a **check**. Don't go on until it passes; the sections
after the quick start explain each part in more detail.

### A. Next to an emulator, on a TV

1. **Flash the SD card.** In Raspberry Pi Imager choose Raspberry Pi Zero 2 W
   and *Raspberry Pi OS (64-bit)*, the **Desktop** image, Trixie or newer.
   In its settings, set:
   - a hostname, e.g. `boresight`
   - a username and password
   - your Wi-Fi
   - **SSH enabled**

   **Check:** the card is written without errors.

2. **Connect the hardware, with the Pi powered off:**
   - the camera's ribbon into the camera connector, as the camera's own
     instructions show
   - the trigger button between **GPIO 17** (header pin 11) and **GND**
     (pin 9)
   - optionally, an LED and resistor from **GPIO 27** (pin 13) to GND
   - HDMI to the TV, then power into the Pi's power port

   **Check:** the Pi boots to its desktop on the TV, logged in.
   Raspberry Pi OS Desktop logs in by itself. If yours asks for a
   password, turn that on with `sudo raspi-config`: *System Options →
   Boot / Auto Login → Desktop Autologin*.

3. **Open a terminal.** Use a keyboard on the Pi's desktop, or SSH from
   your computer:

       ssh <user>@boresight.local

4. **Check the camera:**

       rpicam-hello --list-cameras

   **Check:** your camera is listed. "No cameras available" means the
   ribbon is loose or reversed: power off and reseat it. A USB webcam
   instead shows up in `ls /dev/video*`.

5. **Install the system dependencies, once.** uv, from its official
   installer:

       curl -LsSf https://astral.sh/uv/install.sh | sh

   Then log out and back in. git, a C compiler and the kernel headers
   come with Raspberry Pi OS Desktop. On another system, install them
   with your package manager.

   **Check:** `uv --version`, `git --version` and `gcc --version` each
   print a version.

6. **Let the gun create its pointer.** That means read/write access to
   `/dev/uinput` without root:

       echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/60-uinput.rules
       sudo usermod -aG input $USER

   If `ls /dev/uinput` says there is no such file, the kernel module is
   not loaded. Load it at every boot:

       echo uinput | sudo tee /etc/modules-load.d/uinput.conf

   Then `sudo reboot`, so the group and the rule apply.

   **Check:** after the reboot, `ls -l /dev/uinput` shows the group
   `input`, and `id` lists `input`.

7. **Install the gun:**

       git clone https://github.com/Akay7/Boresight.git ~/Boresight
       cd ~/Boresight
       uv sync --extra gun --extra local

   This takes several minutes on a Zero 2 W, because `evdev` is compiled.

   **Check:** `uv run boresight-gun --help` prints its options.

8. **Write the configuration,** `~/boresight-gun.toml`:

       output = "local"

       [overlay]
       picture_aspect = "4:3"

   Keep `picture_aspect` if the emulator shows the game with bars at the
   sides: the tags then go in those bars. Set it to the picture's shape.
   Remove it if the game fills the screen.

9. **Run it once by hand,** in a terminal on the Pi's desktop. Over SSH
   there is no desktop for the overlay to draw on.

       cd ~/Boresight
       uv run boresight-gun --config ~/boresight-gun.toml

   **Check:**
   - White squares with black tags appear on the TV.
   - Pointed at the TV, the gun logs `... fps, N% solved` every few
     seconds.
   - The mouse cursor follows where you aim, and the trigger clicks.

   If tags are cut off at the TV's edge, set the TV's picture size to
   "Just scan" or "Screen fit". If the TV has no such setting, add
   `extra_margin_px = 30` under `[overlay]` and raise it until they show.
   Stop the gun with Ctrl-C.

10. **Start it at every login:**

        uv run boresight-gun --config ~/boresight-gun.toml --autostart
        sudo reboot

    **Check:** when the desktop comes up, the tags appear by themselves.
    `--autostart remove` undoes it.

11. **Set up your emulator,** whichever you use:
    - it runs **windowed or borderless full screen**, not
      fullscreen-exclusive
    - its light gun (Zapper, Light Phaser…) takes its position from the
      **mouse**
    - the game's shape matches `picture_aspect`

    **Check:** in a light-gun game, shots land where you aim.

### B. A USB mouse for another machine

1. **Flash the SD card** as in A1, with *Raspberry Pi OS Lite (64-bit)*,
   Trixie or newer. No desktop is needed.
2. **Connect the camera and the button** as in A2, with the Pi off. Don't
   connect the USB data cable yet. Power the Pi from its power port for
   now.
3. **Log in over SSH** as in A3.
4. **Check the camera** as in A4.
5. **Install uv** as in A5. If `git --version` fails, install git with
   your package manager (`sudo apt install git` on Raspberry Pi OS).
6. **Install the gun:**

       git clone https://github.com/Akay7/Boresight.git ~/Boresight
       cd ~/Boresight
       uv sync --extra gun

   **Check:** `uv run boresight-gun --help` prints its options.

7. **Set up the USB mouse and the boot service** (root, once):

       sudo deploy/pi/install.sh
       sudo reboot

   **Check:** after the reboot, `ls /sys/class/udc` lists a controller and
   `systemctl status boresight-gun` says `active (running)`.

8. **Put markers around the host's screen.** The host runs nothing, so
   the tags are printed:
   - On any computer with Boresight installed, run `uv run boresight` and
     open `http://127.0.0.1:7331/markers` to print the sheet.
   - Stick each tag where the sheet's diagram says.
   - Measure where each one ended up, as the main README's "Marker
     system" and "markers.toml" describe, and write the result into
     `/etc/boresight/markers.toml` on the Pi.
   - Uncomment `layout = "/etc/boresight/markers.toml"` in
     `/etc/boresight-gun.toml`, and run
     `sudo systemctl restart boresight-gun`.

9. **Plug in the host.** Connect the Pi's USB **data** port, the one
   nearer the middle of the board, to the host.

   **Check:**
   - The host lists a mouse called "Boresight light gun".
   - `journalctl -u boresight-gun -f` shows `... fps, N% solved` while
     you aim at the screen.
   - The host's cursor follows the gun.

## What you need

| Part | Notes |
| --- | --- |
| Raspberry Pi Zero 2 W | The only supported board. Others will likely work and are untested |
| Raspberry Pi OS, **Trixie** (64-bit) | Lite is enough for the USB output. Python 3.12 or later is needed; Bookworm's 3.11 is too old |
| A camera | A CSI camera (Camera Module 3 or similar, with the Zero's small camera cable), or a USB webcam |
| Push button | Between GPIO 17 (header pin 11) and any GND pin. The internal pull-up is used |
| LED and resistor (optional) | GPIO 27 (header pin 13) to the LED, resistor, GND. Without one the state is only logged |
| A USB cable to the host | Into the Pi's **data** port, the one nearer the middle of the board. It also powers the Pi |
| A case (optional) | The printed case in [hardware/case/](../../hardware/case/README.md): the Pi kit, with the Pi on a sled in the barrel and a 14 x 14 x 6 mm heatsink on its processor. It wires the trigger and LED to the pins above. Its cables plug into the Pi from below, through a window under the barrel: HDMI for a TV, and USB to the host. It runs from any battery drawer; for a host cable, fit the tether drawer without its cable, and the hub then runs from the Pi. Take the barrel off to reach the micro-SD card |

Set up the SD card with Raspberry Pi Imager: Trixie, your Wi-Fi and an SSH
user for installing. Wi-Fi is only for you; the gun does not use it.

## System dependencies

Install these yourself, with your system's package manager. Raspberry Pi OS
already ships the ones marked *preinstalled*.

| What | Needed for | Notes |
| --- | --- | --- |
| [uv](https://docs.astral.sh/uv/) | everything | Installs the gun and its Python packages into the checkout's own `.venv` |
| Python 3.12 or later | everything | *Preinstalled* on Trixie. uv can also fetch one |
| git | everything | To clone the repository |
| `rpicam-apps` (the `rpicam-vid` program) | a CSI camera | *Preinstalled*. The gun runs `rpicam-vid` and reads its frames |
| Picamera2 (`python3-picamera2`) | only `[camera] source = "picamera2"` | *Preinstalled*. The venv must see it: create it with `uv venv --system-site-packages` before `uv sync` |
| A C compiler and kernel headers | the `local` output | pip builds `evdev`, the uinput binding, from source: it has no Arm wheel. *Preinstalled* on Raspberry Pi OS (`gcc`, `linux-libc-dev`) |
| A desktop session | the `local` output | The overlay is a desktop window. Raspberry Pi OS **Desktop** (not Lite) has one; any X11 desktop, or a Wayland one with XWayland, works |
| A udev rule for `/dev/uinput` | the `local` output | So the gun can create its pointer without root: the rule and group under "`/dev/uinput` permission" in the [main README](../../README.md) |

Nothing else is needed from the system. OpenCV, NumPy, the GPIO libraries
and the overlay's Qt come from pip as ready-built wheels.

## Install

On the Pi, as for Boresight anywhere:

    git clone https://github.com/Akay7/Boresight.git
    cd Boresight
    uv sync --extra gun
    uv run boresight-gun --help

`--extra gun` adds the GPIO trigger and LED. For the `local` output add
`--extra local` as well: `uv sync --extra gun --extra local`.

### The USB output: start at power-up

The USB mouse needs root once, to put the Pi's USB port in device mode, set
up the HID gadget and install a boot service. From the same checkout:

    sudo deploy/pi/install.sh

It installs no packages. It checks that `uv sync` has been run, copies the
example configuration to `/etc/boresight-gun.toml`, adds
`dtoverlay=dwc2,dr_mode=peripheral` to `config.txt`, and installs two
systemd services: the gadget, and the gun from this checkout's `.venv`. If
the `dtoverlay` line was new, **reboot once**. After that the Pi enumerates
as a mouse whenever it has power and starts aiming without a login.

After `git pull`, run `uv sync --extra gun` again and restart the service.
Running the setup again is only needed if `deploy/pi/` changed.

### From an older install

Earlier versions of `install.sh` installed apt packages and put the program
in `/opt/boresight`. Nothing uses that copy any more. After running the new
`install.sh`, remove it with `sudo rm -r /opt/boresight`. Whether to remove
the apt packages it added is up to you; the gun no longer uses them.

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
- `[camera]`: which camera, its resolution and frame rate, and fixed
  exposure and gain. Exposure is never automatic. `source` is one of:
  - `auto`, the default: `rpicam` where `rpicam-vid` is installed, `webcam`
    otherwise.
  - `rpicam`: a CSI camera, through `rpicam-vid`. The width must be a
    multiple of 64 and the height of 16 (640×480, 1024×768 and 1280×720 are
    fine), or `rpicam-vid` pads its frames. The gun refuses other sizes.
  - `webcam`: a USB webcam through OpenCV. `device` is its index (`0`) or
    path (`"/dev/video0"`). Webcams differ in whether they accept a fixed
    exposure: the log says what was applied, and warns if exposure stayed
    automatic.
  - `picamera2`: a CSI camera through Picamera2. The only source with sensor
    timestamps, but it needs the venv set up as under "System
    dependencies".
- `[pins]`: BCM numbers. Anything that is not a header GPIO, or a trigger and
  LED on the same pin, stops the gun at startup with the pin named.
- `[tuning]`: smoothing, and hold through a dropout, with the server's
  defaults.

Restart after a change: `sudo systemctl restart boresight-gun`.

## Next to an emulator

With `output = "local"` the gun aims at the Pi's own display. Run any
emulator or game on the Pi's desktop, the way you would on a PC: Boresight
does not install, start or configure it. The gun does what the server does
with a phone on a PC:

- the on-screen overlay draws the markers on the display, and the gun
  solves against exactly what it drew
- the cursor moves to where the gun points: a pointer device, like a pen
  tablet
- the trigger is the primary mouse button

Any emulator works if it does two things:

1. **It reads the mouse as its light gun.** Most have a setting for which
   device a light gun or Zapper takes its position from: choose the mouse.
2. **It runs windowed or borderless full screen**, never
   fullscreen-exclusive. No overlay can draw over a fullscreen-exclusive
   window, on any system.

Set up:

1. Flash Raspberry Pi OS **Desktop** with Raspberry Pi Imager, with
   automatic login on.
2. Install as above, with `--extra local`, and add the uinput udev rule.
3. In `/etc/boresight-gun.toml` (or any config file):

       output = "local"

       [overlay]
       picture_aspect = "4:3"   # if the emulator shows the game with bars
       extra_margin_px = 0      # for a TV that overscans and can't be told not to

   With `picture_aspect`, the six tags sit in the bars beside a centred
   picture of that shape, never over the game. Set it to the shape the
   emulator shows (4:3 for most retro systems). Without it, the tags go at
   the screen's corners and edge midpoints.
4. Try it from a terminal on the Pi's desktop:

       uv run boresight-gun --config /etc/boresight-gun.toml

5. Make it start when you log in. This writes a desktop autostart entry
   for your user, and needs no root:

       uv run boresight-gun --config /etc/boresight-gun.toml --autostart

   It restarts the gun if it fails. `--autostart remove` takes it out.

Set the TV to "Just scan" or "Screen fit" (no overscan) so the corner tags
are not cut off; otherwise raise `extra_margin_px` until they show.

The USB setup script is not used for this output. If it was run before,
disable its services with `sudo systemctl disable --now boresight-gun
boresight-gadget`.

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

USB output:

- [ ] `rpicam-vid` accepts the gun's flags, and exposure, gain and white
  balance stay fixed
- [ ] Frame rate and solve rate at 640×480 and 1024×768 (the log line)
- [ ] The host enumerates a mouse with no driver; hosts tried: ______
- [ ] Aim lands where it should, on a host with one display
- [ ] Unplug and replug the cable without a reboot
- [ ] A power cycle ends with a working gun and no login
- [ ] Default exposure and gain are sensible for the camera in use

Local output:

- [ ] The overlay stays above an emulator in windowed or borderless full
  screen on the Pi's desktop
- [ ] After login the overlay is up and the cursor follows the gun, with no
  command
- [ ] In a light-gun game, hits land where aimed, and one pull is one shot
- [ ] Emulator frame rate, tracking fps, CPU and temperature with both
  running: ______
- [ ] All six tags are seen with the TV's overscan on and off;
  `extra_margin_px` needed: ______
