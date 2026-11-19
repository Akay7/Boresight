# Proposal

## Why

Every ESP32-CAM setting — Wi-Fi name and password, server address and
port, token, camera tuning — is compiled into the firmware, so changing
any of them means a rebuild and a reflash through a USB-serial adapter.
On the first real board that meant reflashing to change the token or
the PC's address, and once the board is sealed in the gun there is no
adapter to reflash through. The settings belong on the device, editable
from a phone without tools.

## What Changes

- **Setup mode on the device.** The ESP32-CAM opens a temporary, open
  Wi-Fi network of its own (`Boresight-XXXX`) serving a setup page. It
  enters setup mode when it has no Wi-Fi network configured, or when the
  trigger is held for about 5 seconds while it boots. Joining the network
  from a phone opens the page by itself, like a hotel Wi-Fi login page.
- **The network is temporary.** It closes once settings are saved (the
  device restarts into normal operation), or after 10 minutes with
  nothing saved. A configured board then starts normally. An
  unconfigured one stops with its error pattern until it is reset.
- **What the page edits:** Wi-Fi name (with a list of nearby networks)
  and password, server address and port, token, and camera tuning
  (resolution, JPEG quality, frame-rate cap, exposure, gain). Input is
  validated before anything is stored. Stored passwords and tokens are
  never sent back to the page; leaving their field empty keeps them.
  TLS, the trusted certificate and the pin assignments stay build-time
  settings.
- **Settings live in the device's flash** (NVS) and survive reboots and
  reflashes of the app. The `menuconfig` values become the defaults
  used for anything not set on the device, so a build configured the
  old way still works with no setup. The page can reset the device to
  those defaults.
- **The server can be found without its address.** The server announces
  itself on the local network over mDNS (`_boresight._tcp`) when it is
  bound to a network address. A device whose server address is left
  empty finds it that way, so a changed PC address no longer needs
  reconfiguring. The token is never part of the announcement. The
  announcement can be turned off.
- **A new status LED pattern** shows setup mode, distinct from the
  existing five.
- **The emulator can run setup mode** over its emulated Ethernet,
  entered with a console command, so saving settings from the page is
  covered by the automated end-to-end suite. Discovery is checked on
  hardware only, since the emulator's network does not carry multicast.

## Capabilities

### New Capabilities
- `esp32-cam-setup`: the device's setup mode — when it is entered, the
  temporary network and its lifetime, the setup page and what it may
  change, validation, storage on the device, write-only secrets and
  resetting to the build defaults.
- `server-discovery`: the server announcing itself on the local network,
  what the announcement carries and leaves out, when it is made, and a
  device finding the server through it when no address is configured.

### Modified Capabilities
- `esp32-cam-client`: settings come from the device's stored settings
  over the build defaults, rather than from build-time configuration
  alone; a missing configuration opens setup mode instead of only being
  reported; the status LED gains a setup-mode pattern.
- `esp32-cam-emulation`: setup mode runs in the emulator over emulated
  Ethernet, and the end-to-end suite covers saving settings through it.
- `network-access`: the device details printed at startup say the
  address may be left empty for discovery, and whether the server is
  being announced.
- `runtime-settings`: the settings file's `server` table gains
  `announce`.

## Impact

- **Firmware** (`firmware/boresight-cam/`):
  - New modules: the settings store, setup mode (access point, page
    server, captive-portal DNS) and discovery.
  - `wifi.c`, `link.c`, `camera.c` and `main.c` read the effective
    settings instead of `CONFIG_BORESIGHT_*`.
  - `components/boresight_proto` gains form decoding, settings
    validation, a DNS reply builder and the new LED pattern, all
    host-tested.
  - New managed component `espressif/mdns`, plus the IDF's
    `esp_http_server`. The app grows by an estimated 150–250 KB, within
    the 1.47 MB partition (1.04 MB used today).
- **Emulator:** a `setup` console command, a port forward in
  `tools/run-emulator.sh`, and a new end-to-end test.
- **Server:** a new mDNS announcement using the `zeroconf` package
  (LGPL-2.1, pure Python) in the `server` extra; a `--announce` /
  `--no-announce` flag and `server.announce`; an updated device block at
  startup.
- **Docs:** README "The ESP32-CAM client" (setup mode, the LED pattern,
  discovery) and the firmware README.
- **Compatibility:** no wire-format change. Existing builds keep working.
  A build with `menuconfig` settings needs no setup, though settings
  saved on the device later take precedence over them.
