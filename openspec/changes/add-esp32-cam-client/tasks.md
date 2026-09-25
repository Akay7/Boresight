## 1. Server: session identity

- [x] 1.1 Add `client_kind`, `client_version` and `frame_size` (default
      `None`) to `SessionStats` in `stream.py`; verify existing
      `as_message` tests still pass unchanged (`uv run pytest`)
- [x] 1.2 Handle `{"type": "hello", "client": str, "version"?: str,
      "frame_size"?: [int, int]}` in `server.py`'s `_handle_control`,
      ignoring wrong types; verify with websocket tests: a valid hello
      sets the identity, a hello with a non-string client leaves the
      session unidentified and later frames still solve
- [x] 1.3 Replace the hardcoded "phone connected/disconnected" log
      wording and `client="phone"` default with a client-neutral label
      that includes the kind once known; verify with a `caplog` test that
      an `esp32-cam` session's disconnect line names the kind

## 2. Server: session listing

- [x] 2.1 Add a session registry on `app.state`, registering in
      `stream_frames` after `accept()` and removing in the session's
      `finally`; verify a unit test that the registry is empty after a
      client disconnects, including abruptly
- [x] 2.2 Add `GET /sessions` returning remote address, identity,
      `connected_s` and the stats message without the `debug` key;
      verify tests: a streaming session is listed with its counts and
      `round_trip_ms`, a closed one is absent, a debug-enabled session's
      entry has no `debug` key
- [x] 2.3 Verify with a test that `GET /sessions` returns 401 without the
      token when one is configured and 200 with it

## 3. Server: headless connection details

- [x] 3.1 Add `certificate_fingerprint(certfile)` to `netaccess.py`
      (SHA-256 over DER, colon-separated uppercase hex); verify a test
      that it matches `cryptography`'s fingerprint of a generated
      certificate and is identical across two `resolve_certificate`
      calls
- [x] 3.2 Print a device block in `server.main()` after the phone URL:
      host, port, frame socket path, TLS on/off, token, and under TLS the
      certificate path and fingerprint; verify with a `capsys` test
      calling `main()` with `uvicorn.run` patched, for both TLS and
      plain-text configurations

## 4. Phone client hello

- [ ] 4.1 In `web/capture.js`, send `{"type": "hello", "client": "phone",
      "frame_size": [w, h]}` from the socket's `open` handler on every
      connection; verify manually in a desktop browser against a local
      server that `GET /sessions` lists the session as `phone`, and
      again after reloading the page

## 5. Firmware project scaffold and configuration

- [ ] 5.1 Create `firmware/boresight-cam/` as an ESP-IDF v5.x project
      (`CMakeLists.txt`, `main/`, `main/idf_component.yml` pulling
      `espressif/esp32-camera` and `espressif/esp_websocket_client`,
      `sdkconfig.defaults` with PSRAM enabled and target `esp32`); verify
      `idf.py set-target esp32 && idf.py build` succeeds
- [ ] 5.2 Add `main/Kconfig.projbuild` with Wi-Fi SSID/password, server
      host/port, token, TLS toggle, resolution, JPEG quality, fps cap,
      send timeout, exposure, gain, trigger GPIO (default 13) and
      debounce ms; verify the options appear under `idf.py menuconfig`
- [ ] 5.3 Embed `main/server_cert.pem` when TLS is on, failing the build
      with a message naming the file when it is missing, and needing
      nothing when TLS is off; verify the build passes with TLS off and no
      certificate file present
- [x] 5.4 Add `firmware/boresight-cam/build/`, `sdkconfig`,
      `sdkconfig.old`, `managed_components/` and `main/server_cert.pem`
      to `.gitignore`; verify `git status` shows none of them after a
      configured build
- [ ] 5.5 Boot-time config check: empty SSID or host logs the missing
      setting and enters the error LED state; verify by building with an
      empty SSID and reading the serial log (`idf.py monitor`)

## 6. Platform-independent protocol component

- [x] 6.1 Create `components/boresight_proto` (no IDF includes) with
      `bp_pack_header(double client_ms, uint8_t out[8])`; verify a host
      test asserting the bytes equal a vector produced by
      `boresight.stream.pack_frame(1234.5, b"")`, recorded in the test
      with the Python one-liner that generated it
- [x] 6.2 Add the integrating debouncer (`bp_debounce_update(state,
      level, now_ms) -> event`) emitting only released→pressed events;
      verify host tests: clean press gives one event, bouncy press and
      release give one event, a 5 s hold gives one event, a sub-debounce
      glitch gives none
- [x] 6.3 Add the reserved-pin check for the AI-Thinker pin map (camera
      pins, GPIO0/1/2/3/4/12/15/16); verify host tests accept 13 and 14
      and reject 0, 4, 12 and 16
- [x] 6.4 Add `firmware/boresight-cam/test_host/` (plain CMake + CTest
      building the component with the host compiler); verify
      `cmake -S test_host -B build-host && cmake --build build-host &&
      ctest --test-dir build-host` passes

## 7. Firmware: camera and streaming

- [ ] 7.1 Wi-Fi station bring-up with reconnect and 1 s → 30 s
      exponential back-off; verify on hardware via serial log that the
      device rejoins after the AP is power-cycled
- [ ] 7.2 Camera init with AI-Thinker pins, PSRAM frame buffers,
      `fb_count = 2`, `CAMERA_GRAB_LATEST`, configured resolution and
      quality; disable AEC/AGC and apply exposure and gain; log applied
      settings and the reset reason; verify on hardware from the serial
      log
- [ ] 7.3 WebSocket connection to `ws(s)://host:port/ws/frames?token=…`
      with the embedded certificate as the only trust anchor under TLS
      and built-in auto-reconnect disabled; send `hello` (kind
      `esp32-cam`, version, frame size) on connect; verify against a
      local server that `GET /sessions` lists an `esp32-cam` session
- [ ] 7.4 Capture task: grab, pack header, send header + JPEG as one
      binary message via partial sends with the configured timeout, count
      skips, sleep to the fps cap; verify on hardware that the server's
      `received` rate stays at or below the cap and `/sessions` shows
      `processed` increasing with markers in view
- [ ] 7.5 Refused-token handling (401/403 handshake or 1008 close): error LED, 30 s back-off, no
      tight retry loop; verify by flashing a wrong token and observing the
      server logs show at most one refused attempt per back-off interval
- [ ] 7.6 TLS refusal: verify that with a different certificate embedded
      the handshake fails, the server logs no accepted socket, and the
      error LED pattern shows

## 8. Firmware: buttons

- [ ] 8.1 Button table (GPIO → action, only `trigger` defined) validated
      at boot with the reserved-pin check, internal pull-up, any-edge
      interrupt notifying a high-priority button task running the
      debouncer; verify on hardware that configuring GPIO12 refuses to
      start with the error pattern
- [ ] 8.2 On a press event, send `{"type": "trigger"}` if connected,
      discard otherwise; verify on hardware with the server's fake or
      real backend that 10 presses raise `triggers` in `/sessions` by
      exactly 10, a 5 s hold raises it by 1, and presses while the server
      is down are not delivered after reconnect

## 9. Firmware: telemetry and status LED

- [ ] 9.1 Parse `stats` text messages (`client_ms`, `outcome`,
      `triggers`) with cJSON, discarding messages larger than the receive
      buffer; send `rtt` at most once per second; verify `/sessions`
      shows a non-zero `round_trip_ms` for the device session
- [ ] 9.2 LED task on GPIO33 (active-low) implementing the five patterns
      from design.md, treating stats older than 1 s as unsolved; verify on
      hardware by covering the lens (unsolved pattern) and pointing at
      markers (solid)

## 10. Documentation

- [ ] 10.1 README: add ESP32-CAM to the Hardware table, a "The ESP32-CAM
      client" section (wiring diagram for trigger on GPIO13 to GND, power
      supply requirement, flashing via USB-serial adapter with GPIO0 to
      GND, `menuconfig` settings, copying `.boresight/cert.pem`, reading
      `/sessions`, LED pattern table, plain-text-token trade-off), update
      Repo layout, Future work and Milestones; verify every command in
      the section was run during bring-up
- [x] 10.2 Add `firmware/boresight-cam/README.md` with build, flash and
      host-test commands; verify a clean clone can run the host tests
      from it
- [ ] 10.3 Run `uv run pytest` and `uv run pre-commit run --all-files`;
      verify both pass

## 11. Hardware bring-up (requires an ESP32-CAM, not available in CI)

- [ ] 11.1 End to end over plain `ws://`: device streams, cursor tracks
      aim on the display, trigger clicks at the aim point; record fps,
      round-trip time and drops from `/sessions` in README
- [ ] 11.2 End to end over TLS with `--tls`; record the same numbers and
      the handshake time from the serial log
- [ ] 11.3 Tune default resolution, quality, exposure and gain from 11.1
      and update `sdkconfig.defaults` and README with measured values
