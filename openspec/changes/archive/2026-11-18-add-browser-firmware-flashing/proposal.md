# Proposal

## Why

Getting firmware onto an ESP32-CAM today means Docker, the pinned ESP-IDF
image, a build, `esptool` on the command line, a USB-serial adapter and a
jumper. Every later update repeats all of it, and once the board is
sealed in the gun the adapter cannot reach it at all. With setup mode
(`add-esp32-cam-setup-portal`) the device no longer needs anything
compiled in, so one generic image can serve every gun. What is missing
is a way to get that image onto a board from a browser, both the first
time and every time after.

## What Changes

- **Flashing from a browser over the USB-serial adapter.** A flashing
  page uses the browser's Web Serial support (desktop Chrome or Edge) to
  write a complete image through the same adapter and jumper as today,
  with no Docker, ESP-IDF or `esptool` installed. It shows the
  download-mode steps the adapter cannot do itself (jumper, RST),
  progress, and a clear message in browsers without Web Serial.
- **A project site, with the flasher as one page of it.** The READMEs
  (main, ESP32-CAM firmware, printable case, Pi gun) are rendered as a
  searchable docs site with MkDocs, published on GitHub Pages and kept in
  step with `main`. Its flashing page offers the latest released generic
  image.
- **The same site runs locally.** `mkdocs serve` serves it on
  `localhost` — a secure context, so Web Serial works — and its flashing
  page offers this checkout's firmware build. The Boresight server takes
  no part: flashing a camera and aiming with it stay separate programs.
- **A generic image built and published by CI.** It has no Wi-Fi, server
  or token compiled in, so it boots into setup mode. CI builds it on
  every push, and for a version tag publishes it as a release download
  and on the flashing page.
- **Firmware updates over Wi-Fi from setup mode.** The setup page gains
  a firmware upload. The device checks that the file is a Boresight
  firmware for a board (not the emulator's), writes it to the slot it is
  not running from, and restarts into it. Stored settings are kept. A
  new firmware that fails to start falls back to the previous one by
  itself.
- **A new flash layout.** It has two application slots (each larger
  than today's single one) and the update bookkeeping, with the settings
  area unchanged in place so stored settings survive.
  - **BREAKING (one time):** moving to it takes one last flash over the
    adapter, from the browser or the command line. Wi-Fi updates work
    from then on.
- **The emulator gets the same slots.** The end-to-end suite uploads a
  firmware through the setup page and checks that the device restarts
  into it, and that a device image is refused.

## Capabilities

### New Capabilities
- `firmware-web-flash`: flashing a complete image from a browser over
  the USB-serial adapter — the page, which image it offers published and
  locally, what it writes (settings kept unless erasing is chosen),
  browser support and the download-mode instructions — and the generic
  image CI builds and publishes for it.
- `project-site`: the project's documentation site — built from the
  READMEs, published on GitHub Pages, servable locally, with working links
  and the flasher as one of its pages.
- `esp32-cam-ota`: updating the firmware over Wi-Fi from setup mode —
  the upload, what the device accepts and refuses, the two-slot switch,
  settings surviving it, and falling back when a new firmware does not
  start.

### Modified Capabilities
- `esp32-cam-emulation`: the end-to-end suite also covers a firmware
  upload through setup mode in the emulator.

## Impact

- **Firmware** (`firmware/boresight-cam/`):
  - a two-slot partition table for the device profile (the emulator's
    gets two slots too);
  - bootloader rollback in `sdkconfig.defaults`;
  - an upload handler in `setup_http.c` and an upload control on the
    page;
  - marking a new firmware good once it is running;
  - `boresight_proto` gains the image checks (project name, build kind),
    host-tested;
  - a script that merges the build into the files the flashing page
    writes.
- **Site** (`mkdocs.yml`, `website/`): the MkDocs configuration, a build
  hook that assembles the READMEs (rewriting their repository-relative
  links) and the flashing page, the page itself, and a script fetching ESP Web Tools (Apache-2.0) at a
  pinned version and hash when the site is built (not committed). A
  `docs` dependency group (`mkdocs-material`), outside the default dev
  install. The Boresight server is unchanged.
- **CI:** a firmware job building the generic image in the pinned
  ESP-IDF container, and publishing a GitHub Release on version tags; a
  site job building the docs site strictly on every push and deploying it
  to GitHub Pages from `main`, and again from `main` once a release is
  published, with the latest release's image in the flasher.
- **Docs:** the README and the firmware README get browser flashing,
  Wi-Fi updates and the one-time move to the new layout.
- **Depends on** `add-esp32-cam-setup-portal`: the generic image relies
  on setup mode, and the Wi-Fi upload lives in it. That change has to be
  implemented first.
