# boresight-cam

Firmware that turns an AI-Thinker ESP32-CAM into Boresight's barrel camera
and physical trigger. It streams to the same server and frame socket as the
phone client, in the same wire format, so nothing on the server changes
depending on which device is aiming.

See the main README's "The ESP32-CAM client" section for wiring, power and
the full walkthrough. This file is the build reference.

## Layout

    main/                     the firmware (ESP-IDF v5.x)
      Kconfig.projbuild       every setting, under "Boresight camera"
      main.c                  boot, configuration check, capture loop
      link.c                  frame socket: connect, hello, send, telemetry
      camera.c  wifi.c  buttons.c  status_led.c
      camera_fake.c  net_openeth.c  console.c
                              emulator build only: recorded frames,
                              emulated Ethernet, console buttons
    sdkconfig.emulator        the emulator profile's settings (no secrets)
    partitions_emulator.csv   its partition table (room for the frames)
    tools/idf.sh              idf.py inside the pinned ESP-IDF container
    tools/run-emulator.sh     boot an image in QEMU, in the same container
    components/boresight_proto/
                              wire format, debouncer, pin allowlist,
                              back-off and LED patterns -- no ESP-IDF
                              includes, so it is tested on the host
    test_host/                those tests: plain CMake + CTest

## Host tests (no board, no ESP-IDF)

From this directory:

    cmake -S test_host -B build-host
    cmake --build build-host
    ctest --test-dir build-host --output-on-failure

The frame-header vectors in `test_host/test_proto.c` were generated from
`boresight.stream.pack_frame`; the comment above each one is the command.

## Build without installing ESP-IDF

`tools/idf.sh` runs `idf.py` inside the pinned `espressif/idf:v5.4` image,
so the only thing the host needs is Docker (or Podman, with
`CONTAINER=podman`). It runs as you, so the build output is yours to
delete, and it handles rootless Docker.

    tools/idf.sh device build        # the image for a board
    tools/idf.sh emulator build      # the image for QEMU, see below
    tools/idf.sh device menuconfig

The two profiles build into `build/` and `build-emulator/` from separate
configuration. The emulator's `sdkconfig` lives inside `build-emulator/`,
so building it never touches the device's, which holds your Wi-Fi password
and token.

## Run without a board

Espressif's open-source QEMU, already inside the same image, runs the
emulator build:

    tools/idf.sh emulator build
    tools/run-emulator.sh

QEMU emulates neither the OV2640 nor the Wi-Fi radio, so the emulator build
swaps in three things and nothing else:

- the sensor: eight frames of the project's Blender scene rendered as the
  ESP32-CAM sees it (`tests/fixtures/esp32cam_video/`), served in order,
  repeating, through the real capture, pacing and send path;
- Wi-Fi: QEMU's emulated Ethernet;
- the trigger pin: console commands. Type `press`, `release` or `click` in
  the emulator's console; they feed the real debouncer and send path.

The emulated device dials `10.0.2.2:7391` with token `emulator-token`:
that is the loopback of the machine running QEMU, so a server bound to
`127.0.0.1` is reached with nothing exposed. For example:

    uv run python -m boresight.server --port 7391 --token emulator-token

The boot log says it is an emulator build, and so does the version it sends
in `hello` (`0.1.0+emulator`), so the server can never mistake it for a
board. Quit QEMU with Ctrl-A X.

`BORESIGHT_EMULATOR_BUILD=build tools/run-emulator.sh` boots the *device*
image instead. It has no Ethernet or fake camera, so it only gets through
its boot checks.

### The end-to-end suite

    tools/idf.sh emulator build
    BORESIGHT_EMULATOR_TESTS=1 uv run pytest tests/test_firmware_emulator.py

(the second line from the repository root). It boots the emulator image
against the real server with a recording cursor backend, so nothing moves
your mouse, and checks: identification and streaming, with every solved
position one the same frames replay to; trigger press and release; a
server restart, with a press made while it was down never replayed; and a
refused token reported and not retried within the 30 s back-off. Without
the variable, a Docker that answers and a built image, the normal `pytest`
run skips it and says which is missing.

It found two bugs before any board existed: a refused token was retried
like a network blip, and a server restart was misread as a certificate
mismatch.

What emulation cannot tell you: exposure and gain, rolling shutter,
sensor noise, Wi-Fi throughput and latency, the real frame rate, the LED
and brown-outs. Emulated time is not real time, so the frame rate and
round-trip time the emulator reports mean nothing.

## Build and flash with ESP-IDF installed

Requires ESP-IDF v5.1 or later
([install guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/)).

    idf.py set-target esp32
    idf.py menuconfig          # Boresight camera -> Network, Camera, Pins
    idf.py build

The configuration lands in `sdkconfig`, which is gitignored: it holds your
Wi-Fi password and token. `sdkconfig.defaults` is tracked and holds no
secrets.

The ESP32-CAM has no USB port of its own. Flash through a USB-serial
adapter (3.3 V logic, 5 V to the board's 5V pin), with **GPIO0 held to GND
while it powers up** to enter the bootloader:

    idf.py -p /dev/ttyUSB0 flash monitor

Release GPIO0 and reset the board to run the firmware.

## TLS

With **Connect over TLS** enabled, the build needs the server's certificate
at `main/server_cert.pem` (gitignored) and fails without it:

    cp ../../.boresight/server.crt main/server_cert.pem

The device trusts that certificate and nothing else. At boot it logs the
certificate's SHA-256; the server prints the same figure under `sha256` at
startup. If they differ -- the server's `.boresight/` was regenerated --
copy the certificate again and reflash.
