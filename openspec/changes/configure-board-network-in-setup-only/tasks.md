# Tasks

Requires `add-esp32-cam-setup-portal` to be archived first: this change
modifies requirements that change introduces.

## 1. The board's build configuration has no network settings

- [x] 1.1 In `main/Kconfig.projbuild`, remove the Wi-Fi name and password, and make the server address, port and token `depends on BORESIGHT_EMULATOR` (TLS stays in both); verify `tools/idf.sh device build` leaves no `CONFIG_BORESIGHT_WIFI_*`, `CONFIG_BORESIGHT_SERVER_*` or `CONFIG_BORESIGHT_TOKEN` key in `build/generic/sdkconfig` (a fresh generic build), and `tools/idf.sh emulator build` still has `10.0.2.2`, 7391 and its token
- [x] 1.2 In `main/settings.c`, give a board empty network defaults and port 7331 from a named constant (commented as the server's default), keeping the emulator's Kconfig values and the store-only-if-different rule; verify both profiles build without warnings and the board image contains no network string from the developer's local `sdkconfig` (`strings` on `build/boresight-cam.bin`)
- [x] 1.3 Log a board's network settings as `(device)` or `not set`, and the port as `(device)` or `(default)`, keeping camera `(device)`/`(build)` and the emulator's `(build)`; verify the emulator suite passes (`BORESIGHT_EMULATOR_TESTS=1 uv run pytest tests/test_firmware_emulator.py`) and its boot log shows `(build)` for the server
- [x] 1.4 Firmware README: `menuconfig` lists only camera, pins and TLS for a board, the emulator's built-in server and token are explained, and a stale local `sdkconfig` network section is described as ignored; verify every documented command runs as written

## 2. Start-up and the setup page

- [x] 2.1 Drop `configuration_complete()`'s board branch that points at `menuconfig`, keeping the emulator's missing-address check and the empty-token warning; verify both builds, and that the emulator suite still passes
- [x] 2.2 On the setup page, describe "Reset to build defaults" as forgetting the Wi-Fi, server and token, after which the board opens setup mode by itself; verify the page renders in the emulator (the suite's setup tests) and the token check of `add-esp32-cam-setup-portal` task 3.4 still holds (no response contains the token)
- [ ] 2.3 README "Configure and flash", "Setup mode" and "TLS": the network is set only from the setup page; the command-line flash path no longer configures the network; the one-time move for a board configured through `menuconfig`; verify each instruction against the firmware's behaviour (task 4.x)

## 3. CI

- [x] 3.1 In `.github/workflows/firmware.yml`, replace the check that four options are empty with a check that the generic build's `sdkconfig` has none of those keys, keeping the certificate check; verify the step locally against a fresh generic build, and that it fails when a key is added back by hand

## 4. On the board

Power the board from 5 V.

- [ ] 4.1 Update the bench board, configured through setup mode, over Wi-Fi with the new image; verify it streams with its stored network and token (`(device)` in the boot log) and no setup step
- [ ] 4.2 Reset to build defaults from the setup page; verify the board restarts into setup mode by itself, the page shows no network set and the build's camera values, and saving the network again brings it back to streaming
- [ ] 4.3 Leave the reset board in setup mode for 10 minutes; verify the setup network closes and the board stays on the error pattern until reset (also `add-esp32-cam-setup-portal`'s unconfigured case, tasks 3.5 and 7.4)
- [x] 4.4 Run `uv run pre-commit run --all-files`, the host tests and the emulator suite; verify all pass
      (2026-11-18: all hooks pass, host tests pass, emulator suite 8 passed. Two server tests had read the developer's own `.boresight/config.toml`; `tests/conftest.py` now points the default settings path at an empty directory for every test.)

## Workflow follow-up

- Archive after `add-esp32-cam-setup-portal` is archived, once group 4 is done.
- A release (`v0.1.1` or later) carries it to boards flashed from the site.
