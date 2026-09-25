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

## Build and flash

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

    cp ../../.boresight/cert.pem main/server_cert.pem

The device trusts that certificate and nothing else. At boot it logs the
certificate's SHA-256; the server prints the same figure under `sha256` at
startup. If they differ -- the server's `.boresight/` was regenerated --
copy the certificate again and reflash.
