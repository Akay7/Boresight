# Proposal

## Why

A board's Wi-Fi network and password, server address and port, and token
can come from two places: `menuconfig`, compiled into the firmware, or
setup mode, stored on the device. Every rule about them has to say
which one wins, what "reset to build defaults" leaves, and whether a
board counts as configured, and every check on the bench has to be done
for both. The build path also puts the Wi-Fi password and token inside
the firmware file, which is then uploaded, served and shared like any
other. With setup mode in place, the build path is no longer needed on
a board.

## What Changes

- **Board network settings come only from setup mode.** On a board, the
  Wi-Fi name and password, the server address and port, and the token
  are set from the setup page and stored on the device, and nowhere
  else. The board profile's `menuconfig` no longer has them. The port
  defaults to 7331 until set.
- **A board's firmware never contains them.** Every board image is the
  same as the published generic one, safe to upload, serve or share.
- **Reset forgets the network.** "Reset to build defaults" on the setup
  page erases everything stored: the board is then unconfigured and
  opens setup mode by itself at the next boot, and the camera returns to
  its build defaults.
- **One source per value in the boot log.** Network settings are logged
  as stored on the device or not set; camera settings keep "(device)"
  or "(build)".
- **Kept at build time:** camera defaults and the ranges the page
  allows, the pins, and TLS with its trusted certificate.
- **The emulator keeps its built-in server address, port and token**,
  so the end-to-end suite starts connected with no setup step. Settings
  stored through its setup page still override them.
- **BREAKING (one time, boards only):** a board that relied on
  `menuconfig` network settings, with none stored on the device, starts
  unconfigured after updating and opens setup mode by itself; its
  network is entered once from a phone. A board configured through
  setup mode is unaffected.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `esp32-cam-client`: "Secrets are configured outside version control"
  — on a board, network settings and the token come only from the
  device; build-time configuration supplies them only in the emulator.
- `esp32-cam-setup` (introduced by `add-esp32-cam-setup-portal`): a
  board counts as configured only by what is stored on it; for network
  settings nothing comes from the build; resetting leaves the board
  unconfigured.

## Impact

- **Firmware** (`firmware/boresight-cam/`):
  - `main/Kconfig.projbuild`: the Network menu's Wi-Fi name, password,
    server address, port and token exist only in the emulator profile.
  - `main/settings.c`: board defaults have no network values; the boot
    log's sources follow.
  - `main/main.c` and `main/setup.c`: the "not configured" message no
    longer points at `menuconfig`.
  - `main/setup_http.c`: the reset button's wording.
- **CI** (`.github/workflows/firmware.yml`): the check that the generic
  image has no secrets becomes a check that the options are absent.
- **Docs:** the README's "Configure and flash", "Setup mode" and TLS
  sections and the firmware README stop offering `menuconfig` for the
  network.
- **The developer's local `sdkconfig`:** its network lines no longer
  apply and can be deleted; nothing secret is compiled in any more.
- **Depends on** `add-esp32-cam-setup-portal`: this change modifies
  requirements that change introduces, so it is applied and archived
  after that one.
