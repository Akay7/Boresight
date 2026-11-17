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
- [ ] 4.5 Flash the board from the locally served site's flashing page in Chrome through the CP2104 adapter, without erase; verify it boots with its stored settings, then once with erase and verify it boots into setup mode
      (Needs the board and the adapter.)

## 5. The project site and CI

- [x] 5.1 Add `mkdocs.yml` and `website/hooks.py`: the four READMEs as pages, README-to-page links, copied images, other repository links to GitHub, the flasher and its bundle (from `BORESIGHT_FIRMWARE`, else this checkout's build, else none), served on `127.0.0.1:8000`; a `docs` dependency group with `mkdocs-material`; `.site/` ignored; verify `uv run --group docs mkdocs build --strict` passes and `mkdocs serve` serves the home page, the firmware page with its wiring image, and the flasher with the local build
      (`mkdocs build --strict` passes; `mkdocs serve` served all four pages, the wiring image and the flasher with the local build under /Boresight/, rebuilt on a README edit without looping; a broken link fails the strict build.)
- [x] 5.2 Tests for the hook's link rewriting (README link to page, image copied, source link to GitHub, unknown file reported); verify they pass in the default suite without MkDocs installed
- [ ] 5.3 Add the `firmware` CI workflow: build the device profile in `espressif/idf:v5.4` from `sdkconfig.defaults` only, check the four secret settings are empty and no certificate is embedded, upload a flasher bundle; on `v*` tags check the tag against `PROJECT_VER` and create a GitHub Release with the bundle; verify the steps locally on a fresh generic build, then on a push
      (Written; build, secrets check and bundle run locally on a fresh generic build, which also booted into setup mode in QEMU. Awaiting a push and a first tag.)
- [ ] 5.4 Add the `site` CI workflow: `mkdocs build --strict` on every push and pull request; on `main` and tags deploy to GitHub Pages with the latest release's bundle from `gh release download`, or none before the first release; verify on a push to `main`
      (Written; the strict build with a release-style bundle run locally. Awaiting a push to main.)
- [ ] 5.5 Enable GitHub Pages with the "GitHub Actions" source in the repository settings (one-time, by a maintainer); verify the deploy step succeeds
      (A repository setting for the maintainer.)
- [ ] 5.6 README: the published site and flasher, `mkdocs serve` for the local site and flasher, browser flashing as the first path (Chrome/Edge), the command-line path kept, the Release's app image for Wi-Fi updates; verify each step on the board and the links on the published site
      (Written; to be checked on the board and against the published site.)

## 6. Bring-up on the board

- [ ] 6.1 Move the bench board to the two-slot layout from the browser without erase; verify its stored settings are in effect after boot
- [ ] 6.2 Update it over Wi-Fi from setup mode with a newer build; verify the version in the server's `client identified` line and that settings are kept
- [ ] 6.3 Install the crash-at-boot test image over Wi-Fi; verify the board rolls back by itself and logs it
- [x] 6.4 Run `uv run pre-commit run --all-files`, the host tests and the emulator suite; verify all pass

## Workflow follow-up

- Archive after `add-esp32-cam-setup-portal` is archived (this change's emulation delta builds on that one's text), once group 6 is done.
