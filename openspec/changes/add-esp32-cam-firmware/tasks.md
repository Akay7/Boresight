## 1. Firmware project scaffold and configuration

- [x] 1.1 Create `firmware/boresight-cam/` as an ESP-IDF v5.x project
      (`CMakeLists.txt`, `main/`, `main/idf_component.yml` pulling
      `espressif/esp32-camera` and `espressif/esp_websocket_client`,
      `sdkconfig.defaults` with PSRAM enabled and target `esp32`); verify
      `idf.py set-target esp32 && idf.py build` succeeds
      (Built with `tools/idf.sh device build`, the same idf.py in the pinned ESP-IDF container; see add-esp32-cam-emulator.)
- [x] 1.2 Add `main/Kconfig.projbuild` with Wi-Fi SSID/password, server
      host/port, token, TLS toggle, resolution, JPEG quality, fps cap,
      send timeout, exposure, gain, trigger GPIO (default 13) and
      debounce ms; verify the options appear under `idf.py menuconfig`
      (Checked in the generated `sdkconfig` rather than by opening menuconfig interactively.)
- [x] 1.3 Embed `main/server_cert.pem` when TLS is on, failing the build
      with a message naming the file when it is missing, and needing
      nothing when TLS is off; verify the build passes with TLS off and no
      certificate file present
- [x] 1.4 Add `firmware/boresight-cam/build/`, `sdkconfig`,
      `sdkconfig.old`, `managed_components/` and `main/server_cert.pem`
      to `.gitignore`; verify `git status` shows none of them after a
      configured build
- [x] 1.5 Boot-time config check: empty SSID or host logs the missing
      setting and enters the error LED state; verify by building with an
      empty SSID and reading the serial log (`idf.py monitor`)
      (Verified by booting the unconfigured device image in QEMU: missing SSID and host logged, `state: error`. The LED pattern itself is still for bring-up.)

## 2. Platform-independent protocol component

- [x] 2.1 Create `components/boresight_proto` (no IDF includes) with
      `bp_pack_header(double client_ms, uint8_t out[8])`; verify a host
      test asserting the bytes equal a vector produced by
      `boresight.stream.pack_frame(1234.5, b"")`, recorded in the test
      with the Python one-liner that generated it
- [x] 2.2 Add the integrating debouncer (`bp_debounce_update(state,
      level, now_ms) -> event`) emitting only released→pressed events;
      verify host tests: clean press gives one event, bouncy press and
      release give one event, a 5 s hold gives one event, a sub-debounce
      glitch gives none
- [x] 2.3 Add the reserved-pin check for the AI-Thinker pin map (camera
      pins, GPIO0/1/2/3/4/12/15/16); verify host tests accept 13 and 14
      and reject 0, 4, 12 and 16
- [x] 2.4 Add `firmware/boresight-cam/test_host/` (plain CMake + CTest
      building the component with the host compiler); verify
      `cmake -S test_host -B build-host && cmake --build build-host &&
      ctest --test-dir build-host` passes
- [x] 2.5 Add `BP_BUTTON_RELEASED` to the debouncer and `BP_TRIGGER_DOWN_MESSAGE`/`BP_TRIGGER_UP_MESSAGE` to `boresight_proto`; extend `test_host/test_proto.c` (release with bounce, messages) and verify the host tests pass

## 3. Firmware: camera and streaming

- [ ] 3.1 Wi-Fi station bring-up with reconnect and 1 s → 30 s
      exponential back-off; verify on hardware via serial log that the
      device rejoins after the AP is power-cycled
- [ ] 3.2 Camera init with AI-Thinker pins, PSRAM frame buffers,
      `fb_count = 2`, `CAMERA_GRAB_LATEST`, configured resolution and
      quality; disable AEC/AGC and apply exposure and gain; log applied
      settings and the reset reason; verify on hardware from the serial
      log
- [x] 3.3 WebSocket connection to `ws(s)://host:port/ws/frames?token=…`
      with the embedded certificate as the only trust anchor under TLS
      and built-in auto-reconnect disabled; send `hello` (kind
      `esp32-cam`, version, frame size) on connect; verify against a
      local server that `GET /sessions` lists an `esp32-cam` session
      (Verified in QEMU against a local server; see add-esp32-cam-emulator.)
- [ ] 3.4 Capture task: grab, pack header, send header + JPEG as one
      binary message via partial sends with the configured timeout, count
      skips, sleep to the fps cap; verify on hardware that the server's
      `received` rate stays at or below the cap and `/sessions` shows
      `processed` increasing with markers in view
- [x] 3.5 Refused-token handling (401/403 handshake or 1008 close): error LED, 30 s back-off, no
      tight retry loop; verify by flashing a wrong token and observing the
      server logs show at most one refused attempt per back-off interval
      (Verified in QEMU: 403 reported, error state, no second attempt in 25 s — after fixing the bug the emulator found.)
- [ ] 3.6 TLS refusal: verify that with a different certificate embedded
      the handshake fails, the server logs no accepted socket, and the
      error LED pattern shows

## 4. Firmware: buttons

- [ ] 4.1 Button table (GPIO → action, only `trigger` defined) validated
      at boot with the reserved-pin check, internal pull-up, any-edge
      interrupt notifying a high-priority button task running the
      debouncer; verify on hardware that configuring GPIO12 refuses to
      start with the error pattern
- [ ] 4.2 Add a link session generation counter and send `down`/`up` from `buttons.c`, sending `up` only for a `down` delivered on the current connection; verify with `idf.py build` and on the device (hold drags, press while disconnected is not replayed) (implemented, not yet built or tried on hardware)
      Supersedes the original one-`trigger`-per-press task; on hardware, 10 presses raise `triggers` in `/sessions` by exactly 10, a 5 s hold by 1, and presses while the server is down are not delivered after reconnect
      (Hold and no-replay verified in QEMU through the real debouncer and send path; the GPIO read and a real hold still need a board.)

## 5. Firmware: telemetry and status LED

- [x] 5.1 Parse `stats` text messages (`client_ms`, `outcome`,
      `triggers`) with cJSON, discarding messages larger than the receive
      buffer; send `rtt` at most once per second; verify `/sessions`
      shows a non-zero `round_trip_ms` for the device session
      (Verified in QEMU: `/sessions` shows the device's round-trip time.)
- [ ] 5.2 LED task on GPIO33 (active-low) implementing the five patterns
      from design.md, treating stats older than 1 s as unsolved; verify on
      hardware by covering the lens (unsolved pattern) and pointing at
      markers (solid)

## 6. Documentation

- [ ] 6.1 README: add ESP32-CAM to the Hardware table, a "The ESP32-CAM
      client" section (wiring diagram for trigger on GPIO13 to GND, power
      supply requirement, flashing via USB-serial adapter with GPIO0 to
      GND, `menuconfig` settings, copying `.boresight/cert.pem`, reading
      `/sessions`, LED pattern table, plain-text-token trade-off), update
      Repo layout, Future work and Milestones; verify every command in
      the section was run during bring-up
- [x] 6.2 Add `firmware/boresight-cam/README.md` with build, flash and
      host-test commands; verify a clean clone can run the host tests
      from it

## 7. Hardware bring-up (requires an ESP32-CAM, not available in CI)

- [ ] 7.1 End to end over plain `ws://`: device streams, cursor tracks
      aim on the display, trigger clicks at the aim point; record fps,
      round-trip time and drops from `/sessions` in README
- [ ] 7.2 End to end over TLS with `--tls`; record the same numbers and
      the handshake time from the serial log
- [ ] 7.3 Tune default resolution, quality, exposure and gain from 7.1
      and update `sdkconfig.defaults` and README with measured values
