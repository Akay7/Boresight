# Tasks

Requires `add-esp32-cam-setup-portal` to be implemented first (setup mode,
`setup_http.c`, settings in NVS).

## 1. Image identity (host-tested)

- [x] 1.1 Append `+emulator` to `PROJECT_VER` in the top-level `CMakeLists.txt` when `SDKCONFIG_DEFAULTS` names `sdkconfig.emulator`, and drop the runtime `VERSION_SUFFIX` in `main.c`; verify both profiles build and the emulator's `hello` still reports `0.1.0+emulator` (`BORESIGHT_EMULATOR_TESTS=1 uv run pytest tests/test_firmware_emulator.py`)
- [x] 1.2 Add `bp_app_image_check(head, length, running_is_emulator, version_out)` to `boresight_proto` (image magic, app descriptor magic at offset 32, `project_name`, the `+emulator` kind); verify host tests against checked-in heads of a device and an emulator image (first 256 bytes each, with the command that cut them), plus a random file and a truncated head

## 2. Two-slot layout and rollback

- [x] 2.1 Add `partitions.csv` (nvs `0x9000`/`0x6000` unchanged, otadata `0xf000`, phy `0x11000`, ota_0 `0x20000` and ota_1 `0x200000` at `0x1E0000` each), select it in `sdkconfig.defaults` and `sdkconfig.emulator`, remove `partitions_emulator.csv`; verify both builds and that `flash_args` lists `ota_data_initial.bin` at `0xf000` and the app at `0x20000`
- [x] 2.2 Fail the build in `main/CMakeLists.txt` unless the custom table is selected, naming the lines to change; update the local `sdkconfig` and `build-emulator/sdkconfig`; verify a config with `SINGLE_APP_LARGE` stops with the message
- [x] 2.3 Enable `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE`, mark the app valid on first `streaming` or once setup mode's page is served, and log a rolled-back update at boot; verify the emulator suite still passes and its boot log reports the running slot
- [x] 2.4 Add a test-only Kconfig option that resets at boot (a reset, not an abort: a panic restarts through the CPU-only reset that hangs QEMU); verify in the emulator that an image built with it, installed over the running one, is rolled back on the next boot with the log line
- [x] 2.5 README "The ESP32-CAM client": the new layout and the one-time move over the adapter (settings kept); firmware README likewise; verify the move on the emulator image (old-layout image first, then the new one without erase, settings still in effect)

## 3. Updating over Wi-Fi from setup mode

- [x] 3.1 Add `POST /update` to `setup_http.c`: check the head, stream to the other slot in 4 KB chunks within the slot size, `esp_ota_end`, set the boot slot, confirm and restart; each refusal names its reason on the page; verify both builds
- [x] 3.2 Add the upload control to the setup page (file input, inline script posting the raw file with progress, the result shown); verify the page still renders and works without the script for every other form
- [x] 3.3 Emulator tests: upload `build-emulator/boresight-cam.bin` and see the device restart from `ota_1`, report its version and stream with its stored settings; upload `build/boresight-cam.bin` and see "not an emulator build" with the firmware unchanged; upload a truncated image and see it refused; verify `BORESIGHT_EMULATOR_TESTS=1 uv run pytest tests/test_firmware_emulator.py` passes
- [x] 3.4 README "Setup mode": the firmware upload, which file to use (the app image), what is refused and why, rollback; verify each step in the emulator

## 4. The flasher page

- [x] 4.1 Add `tools/vendor-esp-web-tools.sh <version> [sha512]` (downloads the npm release, checks its SHA-512, keeps `dist/web` and the licence under `website/vendor/esp-web-tools/`, which git ignores), run by the site build when the folder is missing; verify a re-run reproduces the same files byte for byte, a wrong hash is refused, and a build without the folder fetches it
- [x] 4.2 Add `website/flash/index.html`: the instructions (jumper and RST before, after), the install button, the erase choice described as erasing settings, the no-Web-Serial and insecure-context messages with download links, and the no-firmware message; verify in Chrome on `localhost` and over a non-secure origin
      (Checked in headless Chrome on localhost, steps and Connect button shown, and over a non-secure LAN origin: "cannot flash" with the files. Firefox takes that same branch, having no `navigator.serial`.)
- [x] 4.3 Add `website/flasher.py` (no Boresight imports): a bundle (`manifest.json` and `files/`) from a build's `flash_args`, version and build time from the app descriptor, `new_install_prompt_erase`, no Improv wait; runnable on its own; verify tests with a fake build: the four parts at their offsets, `ota_data_initial` present, nothing at NVS, a missing part refused
- [x] 4.4 Remove `/flash` and its files from the Boresight server (router, `create_app` parameter, `main()` wiring, `web/flash`, `web/vendor`); verify a server test that `/flash/` serves no flashing page and the full suite passes
- [x] 4.5 Flash the board from the locally served site's flashing page in Chrome through the CP2104 adapter, without erase; verify it boots with its stored settings, then once with erase and verify it boots into setup mode
      (On the board, 2026-11-18, from the locally served site in Firefox (which has Web Serial; VS Code's built-in browser has not): without erase it booted `running 0.1.0 from ota_0` with `quality 15 (device)` kept; with erase, the generic image opened setup mode by itself.)

## 5. The project site and CI

- [x] 5.1 Add `mkdocs.yml` and `website/hooks.py`: the four READMEs as pages, README-to-page links, copied images, other repository links to GitHub, the flasher and its bundle (from `BORESIGHT_FIRMWARE`, else this checkout's build, else none), served on `127.0.0.1:8000`; a `docs` dependency group with `mkdocs-material`; `.site/` ignored; verify `uv run --group docs mkdocs build --strict` passes and `mkdocs serve` serves the home page, the firmware page with its wiring image, and the flasher with the local build
      (`mkdocs build --strict` passes; `mkdocs serve` served all four pages, the wiring image and the flasher with the local build under /Boresight/, rebuilt on a README edit without looping; a broken link fails the strict build.)
- [x] 5.2 Tests for the hook's link rewriting (README link to page, image copied, source link to GitHub, unknown file reported); verify they pass in the default suite without MkDocs installed
- [x] 5.3 Add the `firmware` CI workflow: build the device profile in `espressif/idf:v5.4` from `sdkconfig.defaults` only, check the four secret settings are empty and no certificate is embedded, upload a flasher bundle; on `v*` tags check the tag against `PROJECT_VER` and create a GitHub Release with the bundle; verify the steps locally on a fresh generic build, then on a push
      (Build, secrets check and bundle run locally on a fresh generic build, which also booted into setup mode in QEMU. The `v0.1.0` tag ran it on GitHub: release `v0.1.0` published with the four parts, the manifest and the app image.)
- [x] 5.4 Add the `site` CI workflow: `mkdocs build --strict` on every push and pull request; on `main`, and again on `main` after `firmware.yml` completes, deploy to GitHub Pages with the latest release's bundle from `gh release download --pattern '*'`, or none before the first release; verify on a push to `main`
      (Deployed from `main` to https://akay7.github.io/Boresight/. The first release run published an empty flasher: without a tag `gh release download` needs `--pattern`, and the failure read as "no release". Fixed in PR #7, which also stopped deploying from tags (refused by the `github-pages` environment); `/flash/manifest.json` then served 0.1.0.)
- [x] 5.5 Enable GitHub Pages with the "GitHub Actions" source in the repository settings (one-time, by a maintainer); verify the deploy step succeeds
      (Enabled by the maintainer; deploys from `main` succeed.)
- [ ] 5.6 README: the published site and flasher, `mkdocs serve` for the local site and flasher, browser flashing as the first path (Chrome/Edge), the command-line path kept, the Release's app image for Wi-Fi updates; verify each step on the board and the links on the published site
      (Written. The page and README name only Chrome and Edge, but Firefox flashed the board (2026-11-18): reword. Still to check against the published site.)

## 6. Bring-up on the board

Power the board from 5 V into its 5V pin, every GND shared, not from the
adapter's 3.3 V: hosting setup mode's network browns it out there and it
restarts into normal operation, which looks like a firmware fault.

- [x] 6.1 Move the bench board to the two-slot layout from the browser without erase; verify its stored settings are in effect after boot
      (The bench board was already on the two-slot layout (moved over the command line). Flashed again from the browser without erase on 2026-11-18: the setting stored on the device (`quality 15 (device)`) was in effect.)
- [x] 6.2 Update it over Wi-Fi from setup mode with a newer build; verify the version in the server's `client identified` line and that settings are kept
      (On the board, 2026-11-18: uploaded from setup mode, it booted `running 0.1.0 from ota_1` with `quality 15 (device)` and streamed. The first attempt was rolled back after a watchdog reset: marking the image good erases a flash sector, and esp32-camera's interrupt, live during the erase, read its overflow message from flash and crashed. The camera is now paused for that write; after that, `camera: paused`, `firmware 0.1.0 started: kept`, no reset. Same version both sides, so the slot, not the version, showed the update.)
- [x] 6.3 Install the crash-at-boot test image over Wi-Fi; verify the board rolls back by itself and logs it
      (On the board, 2026-11-18: the reset-at-boot image installed into ota_0, logged `TEST IMAGE: resetting before start`, and the next boot logged `update to 0.1.0 in ota_0 did not start: rolled back to 0.1.0 in ota_1`, then streamed.)
- [x] 6.4 Run `uv run pre-commit run --all-files`, the host tests and the emulator suite; verify all pass

## Workflow follow-up

- Archive after `add-esp32-cam-setup-portal` is archived (this change's emulation delta builds on that one's text), once group 6 is done.
