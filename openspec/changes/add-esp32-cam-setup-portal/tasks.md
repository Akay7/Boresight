# Tasks

## 1. Pure logic in `boresight_proto` (host-tested)

- [x] 1.1 Add `bp_settings_t` (SSID, password, host, port, token, resolution, JPEG quality, fps cap, exposure, gain) with the limits passed in from the caller; verify host tests build a settings value from defaults
- [x] 1.2 Add `bp_form_decode` for `application/x-www-form-urlencoded` (`+`, `%XX`, bounded output, malformed escapes rejected); verify host tests for spaces, escapes, truncation and a bad `%G1`
- [x] 1.3 Add `bp_settings_apply_form`: validate every field per the esp32-cam-setup spec, write nothing unless all pass, return per-field errors, keep the password/token on empty input and clear them only on the explicit clear flag; verify host tests for port 70000, a 7-character password, an invalid host, an out-of-range camera value, an empty-secret keep and a clear
- [x] 1.4 Add `bp_html_escape`; verify host tests escape `<`, `>`, `&`, `"` and `'` in a hostile SSID
- [x] 1.5 Add `bp_dns_answer`: answer an A query with a given IPv4 address, return an empty answer for other types, reject truncated or malformed packets; verify host tests against captured query bytes from Android and iOS sign-in checks
- [x] 1.6 Add `BP_LINK_SETUP` and the `BP_LED_DOUBLE_BLINK` pattern; verify a host test that it differs from every other pattern over a 3 s window
- [x] 1.7 Add `bp_discovery_tls_ok(txt_tls, built_with_tls)` for the announced-TLS check; verify host tests for match, mismatch and a missing `tls` key
- [x] 1.8 Run `cmake -S test_host -B build-host && cmake --build build-host && ctest --test-dir build-host`; verify all host tests pass

## 2. Effective settings in the firmware

- [x] 2.1 Add `main/settings.c`: fill `bp_settings_t` from Kconfig, overlay keys from NVS namespace `boresight`, log each setting's source (device or build) without logging secrets, and offer save and erase-namespace; verify `tools/idf.sh device build` and `tools/idf.sh emulator build` succeed
- [x] 2.2 Move `nvs_flash_init` before the configuration check in `main.c`, and make the check use the effective settings (board: SSID; emulator: host); verify the emulator boots to `state: streaming` with `sdkconfig.emulator` unchanged
- [x] 2.3 Switch `wifi.c`, `link.c`, `camera.c` and the fps cap in `main.c` from `CONFIG_BORESIGHT_*` to the effective settings, and build the link URI per connection attempt; verify `BORESIGHT_EMULATOR_TESTS=1 uv run pytest tests/test_firmware_emulator.py` passes unchanged

## 3. Setup mode on the board

- [ ] 3.1 Add the boot-time trigger-hold check (input with pull-up, sample up to 5 s if pressed at boot, LED to the setup pattern at 5 s) and the setup/normal branch before the camera starts; verify `tools/idf.sh device build` and, on the board, that a 2 s hold boots normally while a 5 s hold shows the setup pattern
      (Implemented and built; the emulator suite covers the shared page code. Awaiting the check on the board.)
- [ ] 3.2 Add `main/setup_ap.c`: an APSTA scan, then an open SoftAP `Boresight-XXXX` (SoftAP MAC), channel 1, at most 2 stations; verify on the board that the network appears and a phone joins without a password
      (Implemented and built; the emulator suite covers the shared page code. Awaiting the check on the board.)
- [ ] 3.3 Add the captive DNS responder task on UDP 53 using `bp_dns_answer`; verify on the board that a phone joining the network shows its sign-in prompt
      (Implemented and built; the emulator suite covers the shared page code. Awaiting the check on the board.)
- [ ] 3.4 Add `main/setup_http.c` with `esp_http_server`: `GET /` (escaped current values, "set"/"not set" for secrets, network list), `GET /scan`, `POST /save` (validate, store, confirm, restart after ~1.5 s), `POST /reset` (erase namespace, restart), and a catch-all redirect to `/`; verify `tools/idf.sh device build`, and with curl on the board's network that the page never contains the stored token
      (Implemented and built; the emulator suite covers the shared page code. Awaiting the check on the board.)
- [ ] 3.5 Add the one-shot 10-minute setup timer: restart when an SSID is in effect, otherwise stop the AP and park on the error pattern; verify on the board for both a configured and an unconfigured device
      (Implemented and built; the emulator suite covers the shared page code. Awaiting the check on the board.)
- [x] 3.6 Measure the device app size after 3.1–3.4 (`idf.py size` via `tools/idf.sh device size`); verify it fits the factory partition with margin, or switch to a custom partition table and record why
- [ ] 3.7 README "The ESP32-CAM client": a "Setup mode" subsection (when it opens, the network name, what the page edits, the 10-minute lifetime, reset to defaults, the open-network trade-off), the LED table row, and `menuconfig` values described as defaults; firmware README likewise; verify every instruction against the board
      (Implemented and built; the emulator suite covers the shared page code. Awaiting the check on the board.)

## 4. Setup mode in the emulator

- [x] 4.1 Add the `setup` console command (sets the one-shot `setup_next` NVS key and restarts) and serve the setup HTTP handlers on the Ethernet interface in the emulator build, with no AP, DNS or scan; verify on the emulator console that `setup` leads to a setup-mode log line
- [x] 4.2 Add `hostfwd=tcp:127.0.0.1:${BORESIGHT_EMULATOR_SETUP_PORT:-7380}-:80` to `tools/run-emulator.sh`; verify the page loads from 127.0.0.1 with curl, and that nothing listens on other interfaces (`ss -ltn`)
- [x] 4.3 Add emulator tests: an invalid submission (port 70000) is refused, nothing is stored, and the device stays in setup; a wrong token is refused, then `setup` → post the right token → restart → streaming; verify `BORESIGHT_EMULATOR_TESTS=1 uv run pytest tests/test_firmware_emulator.py` passes, and the default run still skips with its reason
- [x] 4.4 Firmware README "Run without a board": the `setup` command, the forwarded port and the new tests; verify each documented command was run

## 5. Server announcement

- [x] 5.1 Add `zeroconf` to the `server` extra with a comment (purpose, LGPL used unmodified); verify `uv sync` and that a core-only install is unaffected (the existing core-only CI check)
- [x] 5.2 Add `server.announce` (default true) with `--announce/--no-announce` under the existing precedence and validation; verify settings tests for the file, both flags and a wrong type
- [x] 5.3 Register `_boresight._tcp` in the lifespan when announcing and bound to a non-loopback address (advertised LAN address, port, TXT `path`, `tls`, `v`), and unregister on shutdown; verify unit tests with a fake zeroconf for registration, no announcement on loopback or with `--no-announce`, unregistration on shutdown, and no token in any property
- [x] 5.4 Extend the startup device block with an `announce` line, and with "leave host empty to discover" only while announcing; verify the existing `capsys` device-block tests extended for on and off
- [x] 5.5 README: discovery in "Running the server" and the settings-file example (`announce`), plus the device block sample; verify with `avahi-browse -rt _boresight._tcp` against a running server that the documented output matches

## 6. Discovery on the device

- [x] 6.1 Add the `espressif/mdns` managed component (device profile), call `mdns_init()` after the network is up, and when the effective host is empty, query `_boresight._tcp` before each attempt, logging every result and connecting to the first IPv4 one; verify `tools/idf.sh device build`, and `idf.py size` still fits
- [x] 6.2 Treat a TXT `tls` that disagrees with the build as a configuration error (error pattern, maximum back-off, a log naming the mismatch); verify with the host test from 1.7 and a device build
- [ ] 6.3 README: leaving the address empty, what the device logs when it finds a server, and the TLS-mismatch message; verify on the board (task 7.3)
      (Implemented and built; the emulator suite covers the shared page code. Awaiting the check on the board.)

## 7. Hardware bring-up (ESP32-CAM, phone, PC)

- [ ] 7.1 Erased board: flash, confirm setup opens by itself, join from a phone, the sign-in page appears, save Wi-Fi, an empty address and the token, and confirm it restarts and streams; record the time from joining to streaming in the README
- [ ] 7.2 Configured board: a 5 s trigger hold at boot opens setup, changing only the JPEG quality keeps the stored password and token, and the board streams with the new quality (`camera: applied` log); reset to defaults restores the build values
- [ ] 7.3 Discovery: the board with an empty address finds the server; after the PC's address changes and the server restarts it reconnects without reconfiguration; a TLS server with a plain-text build is refused with the mismatch logged
- [ ] 7.4 Lifetime: left alone, setup closes after 10 minutes, with the configured board reconnecting and the unconfigured board parked on the error pattern
- [x] 7.5 Run `uv run pre-commit run --all-files` and the host tests; verify both pass

## Workflow follow-up

- Archive the change once the hardware bring-up in group 7 is done and reviewed.
