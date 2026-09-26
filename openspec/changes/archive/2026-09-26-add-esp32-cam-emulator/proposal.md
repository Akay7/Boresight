## Why

The ESP32-CAM firmware (`add-esp32-cam-firmware`) has been written but
never compiled, and every one of its remaining checks waits on a board.
Most of what could go wrong is above the camera sensor: the WebSocket
client, fragmented frame sends, `hello`, `rtt`, trigger press and
release, reconnection and token refusal. All of that can be exercised
without hardware and without proprietary tools: Espressif's open-source
QEMU fork emulates the ESP32 and is already in the ESP-IDF Docker image.
No emulator models the OV2640 or Wi-Fi, so those two are substituted at
the driver boundary and everything above them runs as it would on a board.

## What Changes

- An ESP32-CAM render profile for the existing Blender fixture
  generator: the same scene and camera path, rendered at the firmware's
  default resolution through the OV2640's wider stock lens, with a noisier
  sensor and heavier JPEG. It produces a new checked-in fixture,
  `tests/fixtures/esp32cam_video/`, with per-frame ground truth. The
  existing `synthetic_video` fixture is left byte-for-byte unchanged.
- The firmware's default resolution moves from 800×600 to 1024×768: at
  800×600 the device fixture's markers are too small to solve reliably,
  and 1024×768 is the smallest size that solves every frame.
- The replay accuracy test runs against the new fixture too, so whether
  the device's default resolution is enough is measured, not assumed.
- A containerised build: one script builds the firmware in the pinned
  `espressif/idf` Docker image, so nothing is installed on the host. It
  builds both the device image and an emulator image.
- An emulator build profile, kept apart from the device build (its own
  configuration and build directory), which:
  - brings the network up over QEMU's emulated Ethernet instead of Wi-Fi,
    reaching the server on this machine's loopback, with nothing exposed;
  - replaces the camera sensor with a fake that serves the checked-in
    rendered fixture frames, so the server solves exactly what the
    existing replay tests solve;
  - accepts `press` and `release` on the serial console, fed through the
    real debouncer and trigger send path in place of the GPIO level.
- The firmware logs every link-state change (joining network,
  connecting, streaming, error) on the console, on hardware too, since
  the LED is not the only thing that should be able to say it.
- A script that runs the emulator image in QEMU.
- An opt-in pytest end-to-end suite that boots the emulator image
  against a real server with the fake cursor backend and checks
  streaming and solved positions, trigger hold, reconnect after a server
  restart, presses while disconnected not being replayed, and token
  refusal with back-off.

## Capabilities

### New Capabilities
- `esp32-cam-emulation`: building the firmware without a local toolchain,
  and running it in QEMU against a real server with recorded frames,
  console-driven buttons and an automated end-to-end check.

### Modified Capabilities
<!-- none: `esp32-cam-client` is still an unarchived change
     (add-esp32-cam-firmware); nothing this change adds alters its
     requirements for a real board. -->

## Impact

- New: `firmware/boresight-cam/tools/` (Docker build and QEMU run
  scripts), `sdkconfig.emulator`, `partitions_emulator.csv`,
  `main/camera_fake.c`, `main/net_openeth.c`, `main/console.c`,
  `tests/test_firmware_emulator.py`.
- Changed: `main/` gains a camera frame interface and a
  network-neutral start/wait interface (`wifi.c` implements it for
  hardware), `main/status_led.c` logs state changes, `buttons.c` takes
  injected levels in emulator builds, `boresight_proto` gains JPEG
  dimension parsing with host tests.
- Unblocks the build-only tasks of `add-esp32-cam-firmware` (1.1–1.3)
  and most of its socket behaviour, verified in emulation; camera,
  Wi-Fi, LED and timing on real hardware remain its own tasks.
- Requires Docker for the build and the emulator suite; the suite is
  skipped, with the reason, where Docker or the built image is missing.
- Depends on `add-esp32-cam-firmware`, `add-esp32-cam-client` and the
  archived `trigger-hold` capability.
