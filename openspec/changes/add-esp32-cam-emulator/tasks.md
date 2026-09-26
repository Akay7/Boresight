## 1. ESP32-CAM render profile and fixture

- [x] 1.1 Move resolution, FOV, degradation, JPEG quality and output
      directory in `tests/generate_synthetic_video_fixture.py` into a
      `RenderProfile` with `phone` (current values, default) and
      `esp32cam` profiles, selected by `--profile`; verify by generating
      the `phone` profile's manifest without rendering and diffing it
      against the checked-in `synthetic_video/manifest.json` (no change)
- [x] 1.2 Render `tests/fixtures/esp32cam_video/` with
      `uv run python -m tests.generate_synthetic_video_fixture --profile
      esp32cam`; verify 20 frames at the firmware's default resolution, a manifest recording every
      parameter, and `git status` showing no change under
      `tests/fixtures/synthetic_video/`
- [x] 1.3 Parametrise `tests/test_solve_video_e2e.py` over both fixtures
      with per-fixture tolerances; set the device fixture's from its first
      run and record the measured maxima in a comment; verify
      `uv run pytest tests/test_solve_video_e2e.py` passes. If any device
      frame fails to solve, stop and report it rather than loosen the test
      (At 800x600 the device fixture failed: markers ~18 px, 12/20 frames extrapolated, error up to 276 mm. A sweep passed at 1024x768 (2.9 mm), 1280x720 (2.2 mm) and 1600x1200 (1.8 mm). With the user's agreement the firmware default moved to 1024x768 and the fixture was re-rendered there: 6-8 of 8 markers per frame, all inside the hull, error max 2.92 mm, deltas 1.50 mm; tolerances 6 mm / 4 mm.)

## 2. Containerised build

- [x] 2.1 Add `firmware/boresight-cam/tools/idf.sh <device|emulator>
      <idf.py args…>` running `espressif/idf:v5.4` as the invoking user
      with the repository mounted (honouring `CONTAINER=podman`); verify
      `tools/idf.sh device build` runs and its output is owned by the user
- [x] 2.2 Fix whatever the first device build reports until
      `tools/idf.sh device build` succeeds from tracked defaults only;
      then tick `add-esp32-cam-firmware` 1.1–1.3 where their build-level
      checks are met, noting that menuconfig was checked non-interactively
      (Two errors fixed: missing `esp_app_format` requirement, `xTaskNotifyGiveFromISR` -> `vTaskNotifyGiveFromISR`. `tools/idf.sh` also detects rootless Docker, where `--user` breaks writes.)
- [x] 2.3 Ignore `firmware/*/build-emulator/`; verify with
      `git check-ignore` after an emulator build

## 3. Emulator profile

- [x] 3.1 Add `CONFIG_BORESIGHT_EMULATOR` to `Kconfig.projbuild`, plus
      `sdkconfig.emulator` (no PSRAM, openeth, 4 MB flash,
      `partitions_emulator.csv`, server `10.0.2.2:7391`, token
      `emulator-token`, TLS off) and source selection in
      `main/CMakeLists.txt`; verify the device build is unchanged and
      `tools/idf.sh emulator build` configures
- [x] 3.2 Rename `wifi_start`/`wifi_wait_connected` to
      `network_start`/`network_wait_connected`, and add `net_openeth.c`
      (open_eth MAC, generic PHY, DHCP, same connected bit); verify both
      profiles build
- [x] 3.3 Append `+emulator` to the version logged at boot and sent in
      `hello`, and skip the SSID check in emulator builds; verify with the
      boot log in 5.1

## 4. Fake camera

- [x] 4.1 Add `bp_jpeg_dimensions()` to `boresight_proto`; verify host
      tests with a hand-built SOF header, a truncated input, and a real
      device-fixture frame located via a compile definition
      (The real-file test uses the phone fixture's frame 1, a stable 1280x720, so it does not move with the device fixture's resolution.)
- [x] 4.2 Introduce `camera_grab`/`camera_release` in `boresight_cam.h`,
      move `camera.c` and the capture loop in `main.c` onto them; verify
      the device build
- [x] 4.3 Add `camera_fake.c` serving `esp32cam_video` frames 1–8 in
      rotation, embedded by CMake with an `FF D8` check that fails the
      build naming the file and `git lfs pull`; verify by building with a
      pointer file substituted (expect the failure) and then normally
      (The check is also a configure dependency: without that, an already-configured build embedded a pointer file unchecked — found by this verification.)

## 5. Console and state logging

- [x] 5.1 Log `state: <name>` on every link-state change in
      `status_led.c`; verify in the emulator boot log
- [x] 5.2 In emulator builds, have `buttons.c` read an injected level via
      `buttons_inject()`, and add `console.c` reading `press`, `release`
      and `click` from the console; verify by typing them in a manual
      emulator run against a server and seeing the hold in its log

## 6. Running the emulator

- [x] 6.1 Add `tools/run-emulator.sh` (merge the flash image, run QEMU in
      the container with `--network host`, open_eth user networking, the
      watchdog disabled and the console on stdio); verify a manual boot
      reaches `state: streaming` against `uv run python -m
      boresight.server --port 7391 --token emulator-token` and that
      `/sessions` lists the device with the fixture's frame size
      (Verified against the real app with the fake cursor backend on 127.0.0.1:7391 rather than `boresight.server`, which would open uinput and move the real mouse. Also: `BORESIGHT_EMULATOR_BUILD=build` boots the device image, with `-m 4M` for its PSRAM.)

## 7. End-to-end suite

- [x] 7.1 Add `tests/test_firmware_emulator.py` (marker `emulator`
      registered in `pyproject.toml`; skipped with a reason unless
      `BORESIGHT_EMULATOR_TESTS=1`, Docker answers and an emulator image
      is built), with fixtures for a restartable loopback server on a
      shared `FakeCursorBackend` and a module-scoped emulator with a
      console reader; verify a plain `uv run pytest` skips it with the
      stated reason
- [x] 7.2 Test identification and streaming: `esp32-cam` session,
      `+emulator` version, the fixture's frame size, and every solved
      position within the replay's set; verify it passes
- [x] 7.3 Test trigger hold: `press` holds the backend's button and
      `release` lets go, and the `triggers` count reaches the server;
      verify it passes
- [x] 7.4 Test a restarted server: the device reconnects on its own, and
      a `press`/`release` while the server is down never reaches it;
      verify it passes
- [x] 7.5 Test token refusal (last in the module): the console reports
      the refusal and the server logs no second attempt within 25 s;
      verify it passes
      (The emulator found two firmware bugs here and in 7.4, both fixed in `link.c`: a 403 was retried as a network blip because the client reports it under a transport error type, and a plain connection reset was read as a certificate mismatch from a meaningless verify-flags value.)
- [x] 7.6 Run the whole suite with `BORESIGHT_EMULATOR_TESTS=1` and the
      default suite without it; verify both pass
      (Emulator suite: 4 passed with the 1024x768 frames. Default run: 479 passed, the 4 emulator tests skipped with their reason.)

## 8. Documentation

- [ ] 8.1 `firmware/boresight-cam/README.md`: Docker build, emulator run,
      console commands and the e2e suite; README "The ESP32-CAM client":
      a short "Without a board" subsection, and the Testing section:
      the device fixture and what it does and does not model; verify each
      documented command was run in this change
      (Written in both READMEs. Every command in them was run except `uv run python -m boresight.server --port 7391 --token emulator-token`, for the reason in 6.1.)
- [x] 8.2 Run `uv run pre-commit run --all-files` and the host tests;
      verify both pass
