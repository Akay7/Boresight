# Design

## Context

See proposal.md for why. The current state that shapes the approach:

- **Flash layout.** The device profile uses
  `CONFIG_PARTITION_TABLE_SINGLE_APP_LARGE`: NVS at `0x9000` (24 KB), PHY
  data at `0xf000`, and one 1.47 MB factory app at `0x10000`. The app is
  1.10 MB with setup mode and discovery. The emulator uses
  `partitions_emulator.csv`, a 3 MB factory slot sized for its embedded
  frames; its app is 1.2 MB.
- **Settings survive only if NVS stays put.** NVS at `0x9000` holds the
  `boresight` namespace written by setup mode (`add-esp32-cam-setup-portal`).
- **Local configs don't follow `sdkconfig.defaults`.** An existing
  `sdkconfig` keeps its partition-table choice when the defaults change,
  as it did for `CONFIG_HTTPD_MAX_REQ_HDR_LEN`.
- **Setup mode already has the pieces.** It serves its page from
  `setup_http.c` (`esp_http_server`) on its own access point, or on the
  emulated Ethernet. Leaving setup mode is always a restart
  (`boresight_restart()`).
- **The build kind is only known at runtime.** The emulator profile is
  built with
  `-D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.emulator"` (see
  `tools/idf.sh`). It marks its version `+emulator` only at runtime
  (`VERSION_SUFFIX` in `main.c`), not in the image.
- **The server.** Static pages come from `src/boresight/web/`, mounted
  last. Every route is behind the token. It is normally started from the
  repository root (`uv run boresight`), where `.boresight/` also lives.
- **CI.** It runs the firmware host tests, but never builds the device
  image or publishes anything. The repository is on GitHub
  (`Akay7/Boresight`).
- **Web Serial.** It exists in desktop Chromium browsers only, and only
  in a secure context: HTTPS, or `http://localhost`.

## Goals / Non-Goals

**Goals:**
- A person with a board, an adapter and Chrome can get a working gun
  without installing anything. Every later update is over Wi-Fi.
- Settings stored on the device survive every path: browser flashing
  without erase, Wi-Fi updates, and the one-time move to the new layout.
- A bad update can't brick a sealed gun: an image that does not start
  rolls back without anyone touching the board.

**Non-Goals:**
- Pushing updates from the server to devices, or devices checking for
  updates on their own.
- Signed images or secure boot: an upload is gated by setup mode's
  physical trigger hold, as settings are.
- Flashing from Firefox, Safari or a phone browser (no Web Serial).
- Wi-Fi provisioning over serial (ESP Web Tools' Improv); setup mode does
  that.

## Decisions

### 1. Two application slots, NVS left where it is
One custom table, `partitions.csv`, for both profiles:

| Name | Type | Offset | Size |
| --- | --- | --- | --- |
| nvs | data/nvs | `0x9000` | `0x6000` (unchanged) |
| otadata | data/ota | `0xf000` | `0x2000` |
| phy_init | data/phy | `0x11000` | `0x1000` |
| ota_0 | app | `0x20000` | `0x1E0000` (1.875 MB) |
| ota_1 | app | `0x200000` | `0x1E0000` |

The table ends at `0x3E0000` within 4 MB. Each slot has about 70% room
over today's app. The emulator's 1.2 MB app fits, so
`partitions_emulator.csv` goes away. NVS keeps its offset and size, so
the `boresight` namespace survives the move. PHY calibration moves and is
simply redone once (one log line).

An existing `sdkconfig` would keep `SINGLE_APP_LARGE`. So
`main/CMakeLists.txt` fails the build unless the custom table is
selected, naming the two lines to change, the same pattern
`setup_http.c` uses for the header length. The local configs are updated
once during implementation.

- *Alternative:* keep the factory slot and add one OTA slot. Rejected:
  the factory image could never be updated over Wi-Fi, and a sealed gun
  would be stuck on whatever the adapter last wrote there.

### 2. Rollback by the bootloader, marked good on reaching a known state
`CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y`:
- A new image boots `PENDING_VERIFY`.
- `esp_ota_mark_app_valid_cancel_rollback()` is called when the link
  first reaches `streaming`, or when setup mode's page is served.
  Reaching setup mode counts, so a gun on a new network can still be
  reached to fix things.
- A reset before that makes the bootloader return to the other slot.
  Boot then checks `esp_ota_get_last_invalid_partition()` and logs
  "update to <version> did not start: rolled back".

This needs the new bootloader, which comes with the one-time serial
flash anyway.

- *Alternative:* mark the image good after N seconds of uptime. Rejected:
  a firmware that boots but can't connect would be kept, and the gun left
  unreachable if setup mode were also broken.

### 3. The build kind and project live in the image
The top-level `CMakeLists.txt` checks, before `project()`, whether
`SDKCONFIG_DEFAULTS` names `sdkconfig.emulator`. If so it appends
`+emulator` to `PROJECT_VER`, so the image's own `esp_app_desc_t` says
what it is. The runtime `VERSION_SUFFIX` goes away, since the descriptor
already carries it. A pure `bp_app_image_check()` in `boresight_proto`
reads an image's head and returns one of OK, NOT_FIRMWARE, OTHER_PROJECT
or WRONG_KIND, plus the version. It checks:
- the image header's magic;
- the app descriptor's magic at its fixed offset (32);
- `project_name == "boresight-cam"`;
- the `+emulator` suffix against the running build.

It is host-tested against the heads of real built images, checked in as
small fixtures.

- *Alternative:* a separate project name for the emulator. Rejected: the
  project name is fixed before the configuration is read, and the
  version already carries the distinction to the server.

### 4. Upload over plain HTTP in setup mode, streamed to the slot
`POST /update` takes the raw image as `application/octet-stream`. The
page sends the file with a few lines of inline script for progress,
since nothing can be fetched from elsewhere on the setup network. The
handler then:
1. reads the first 256 bytes and runs `bp_app_image_check()`, refusing
   with a reason;
2. `esp_ota_begin(next slot)`, then streams `esp_ota_write()` in 4 KB
   chunks, refusing anything over the slot size;
3. `esp_ota_end()`, which verifies the image's length, checksum and
   SHA-256 and refuses a truncated or corrupted upload;
4. `esp_ota_set_boot_partition()`, confirms on the page, and
   `setup_done()` restarts.

Anything short of step 4 leaves the boot slot unchanged.

- *Alternative:* multipart form upload without script. Rejected: it
  needs a multipart parser in the firmware for one field. A raw body is
  simpler and its size is known.

### 5. Browser flashing with ESP Web Tools, fetched at a pinned version
ESP Web Tools (Apache-2.0, maintained by the ESPHome project) provides
the install button, the serial-port picker, progress, the erase prompt
and chip detection, on top of `esptool-js`. A pinned release's
`dist/web` is fetched into `website/vendor/esp-web-tools/` (ignored by
git) by `tools/vendor-esp-web-tools.sh <version>`, together with its
licence, and checked against the registry's SHA-512. The site build runs
the script when the folder is missing, so a checkout needs the network
once and keeps the copy afterwards. Not committed: 532 KB of minified,
generated code would only be noise in history, and the pin and hash give
the same guarantee that the page runs exactly the reviewed version. The manifest sets `new_install_prompt_erase: true` (erase
is the user's explicit choice) and waits for no Improv.

The image is written as four parts from the build's `flash_args`:
bootloader at `0x1000`, partition table at `0x8000`,
`ota_data_initial.bin` at `0xf000` and the app at `0x20000`. Not one
merged 4 MB blob, which would rewrite NVS and lose the settings.
`ota_data_initial` resets the boot slot to `ota_0`. Without it, a board
that had updated over Wi-Fi to `ota_1` would keep booting its old image
after being reflashed.

The page (`website/flash/index.html`) wraps the button in our own
instructions: the jumper and RST before, removing the jumper and RST
after, and what "did not answer" means. A browser without
`navigator.serial` or a secure context gets the explanation and download
links instead.

- *Alternative:* `esptool-js` directly, with our own UI. Rejected: it
  rebuilds what ESP Web Tools already does well.
- *Alternative:* load ESP Web Tools from a CDN. Rejected: the page would
  run whatever the CDN serves, and nothing would work offline.
- *Alternative:* commit the fetched copy (built that way first, then
  changed). Rejected by the maintainer: generated code in the repository,
  for no guarantee the pinned hash does not already give.

### 6. The site: MkDocs over the READMEs, with the flasher inside
MkDocs with the Material theme builds the site; `mkdocs.yml` sits at the
repository root, and `mkdocs serve` is the one local command. The
READMEs stay where they are and remain the only copy. A build hook
(`website/hooks.py`, run before every build and rebuild) assembles them
into an ignored `.site/docs/`:
- each README becomes a page (main as the home page, then firmware, case
  and Pi gun);
- links to another README become links to its page;
- images are copied next to the page and their paths rewritten;
- links to any other repository file become GitHub links, since the
  site does not carry the source;
- `mkdocs build --strict` turns anything unresolved into a failure.

The hook also copies `website/flash/` and `website/vendor/` in, as static
files, and puts a firmware bundle (manifest plus files) under `flash/`.
The bundle comes from `BORESIGHT_FIRMWARE`, which names either a build
directory (its `flash_args` is read) or a ready bundle (CI's, from the
latest release). Unset, it uses this checkout's
`firmware/boresight-cam/build` if one exists, and nothing otherwise, which
the page explains. Bundling lives in `website/flasher.py`, plain Python
with no Boresight imports, also runnable on its own.

`mkdocs serve` binds `127.0.0.1:8000`: `localhost` is a secure context,
so Web Serial works with no TLS.

The Boresight server keeps none of this: no `/flash` route, no firmware
files, no vendored script in its package.

- *Alternative:* the server serving `/flash` for local builds (built
  first, then dropped). Rejected by the maintainer: flashing and aiming
  are separate programs, and the server should not carry the other's
  files.
- *Alternative:* a `docs/` tree of hand-maintained pages. Rejected: a
  second copy of the READMEs drifts.

### 7. CI: the generic image, releases, and the site
`firmware.yml`:
- **build:** builds the device profile in `espressif/idf:v5.4` with only
  `sdkconfig.defaults` (no secrets), on every push and pull request,
  checks that nothing secret went in, and uploads a flasher bundle.
- **release** (on `v*` tags only): checks the tag against `PROJECT_VER`,
  then creates a GitHub Release with the bundle's files and manifest.

`site.yml`, on every push and pull request:
- builds the site strictly;
- on `main` and on tags, also deploys it to GitHub Pages, with the latest
  release's bundle fetched by `gh release download` at build time (no
  CORS involved).

Before the first release the flashing page says there is no firmware
yet. Enabling Pages ("GitHub Actions" source) is a one-time repository
setting.

## Risks / Trade-offs

- **[Risk]** Anyone in setup mode's radio range can upload firmware. →
  **Mitigation:** setup mode on a configured board still needs the
  trigger held at boot, closes after 10 minutes, and accepts only
  Boresight images of the right kind. It is documented beside the
  settings trade-off. Signing (secure boot) is a later change, and would
  make the published image one key's.
- **[Risk]** The one-time move to two slots needs the adapter again. →
  **Mitigation:** it is one browser flash without erase, so settings are
  kept. The README calls it out, and a board on the old layout keeps
  working until then. It just can't update over Wi-Fi.
- **[Risk]** ESP Web Tools' Improv detection or erase defaults change
  between versions. → **Mitigation:** the version and its hash are pinned;
  updating is a deliberate run of the vendor script.
- **[Risk]** The flashing page's `ota_data_initial` part being omitted by
  mistake would make reflashing look like it failed. →
  **Mitigation:** the manifest is generated from `flash_args`, which
  lists it, and a server test asserts the part is present.
- **[Trade-off]** Browser flashing needs desktop Chrome or Edge. →
  **Mitigation:** the command-line path stays documented, and the page
  links the image files for it.
- **[Risk]** READMEs written for GitHub render differently in MkDocs:
  heading anchors, relative links. → **Mitigation:** the hook rewrites
  links, and `--strict` in CI fails on anything unresolved, so a README
  change that breaks the site is caught on its pull request.
- **[Trade-off]** Rollback is tested in the emulator (an image built to
  crash at boot) and on hardware once. → **Mitigation:** both are tasks.
  The bootloader logic itself is ESP-IDF's.

## Migration Plan

1. **Ship the firmware.** It has the two-slot table, the rollback
   bootloader and the upload. The build check makes stale local configs
   say what to change.
2. **Move each existing board once** over the adapter, with the browser
   page or `esptool`, without erasing: NVS is untouched, and the board
   comes up with its settings.
3. **Update over Wi-Fi from then on:** hold the trigger at boot, open
   setup, upload the app image.
4. **Rollback:** reflashing an older single-slot image over the adapter
   still works, and NVS is untouched either way. Wi-Fi updates are
   unavailable on it.
