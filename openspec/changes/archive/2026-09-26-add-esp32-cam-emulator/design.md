## Context

The firmware (`add-esp32-cam-firmware`) talks to the hardware in three
places: `camera.c` (OV2640 via `esp32-camera`), `wifi.c` (station mode)
and `buttons.c` (`gpio_get_level`). Everything else — `link.c`, the
capture loop in `main.c`, `status_led.c`'s state machine and
`boresight_proto` — is hardware-independent in behaviour, if not in
includes.

`espressif/idf:v5.4` (already pulled) ships `qemu-system-xtensa` built
for the `esp32` machine. That QEMU emulates the CPU, flash, UART, timers
and an OpenCores Ethernet MAC (`open_eth`), which ESP-IDF drives with
`CONFIG_ETH_USE_OPENETH`. It does not emulate the Wi-Fi radio or the
camera interface, and GPIO input cannot be driven from outside.

## Goals / Non-Goals

**Goals:**
- Compile the real firmware with no host toolchain.
- Run the real `link.c`, capture loop, debouncer and press/release logic
  unmodified in emulation, against the real server.
- Make the result a repeatable test, not a manual demo.

**Non-Goals:**
- Emulating the OV2640, exposure, rolling shutter or sensor timing.
- Emulating Wi-Fi, its throughput, latency or reconnect behaviour.
- Verifying the LED's GPIO output or pin-level debounce electrics.
- TLS in emulation. The emulator profile builds plain `ws://`; TLS
  pinning stays a hardware bring-up task (it could be added later by
  embedding a test certificate, with no change to this design).
- Running the emulator suite in the default `pytest` run or in CI.

## Decisions

### Frames: the existing Blender scene, rendered as the ESP32-CAM sees it

`tests/generate_synthetic_video_fixture.py` already renders a lit 3D
scene along a keyframed camera path in Blender 5.2 (installed here), with
ground truth from the camera's own pose, then degrades and JPEG-encodes
each frame. Its resolution, field of view, degradation and JPEG quality
are module constants. They become a `RenderProfile`, selected with
`--profile`:

| | `phone` (existing, default) | `esp32cam` (new) |
| --- | --- | --- |
| Resolution | 1280×720 (16:9) | 1024×768 (4:3), the firmware's default XGA |
| Horizontal FOV | 45° | 55°: the stock ESP32-CAM lens is sold as about 66° diagonal, which at 4:3 is about 55° across |
| Noise sigma | 4.0 | 8.0: a small sensor at fixed gain |
| Blur | 5 px, sigma 1.0 | 5 px, sigma 1.2: a cheaper lens |
| JPEG quality | 88 | 70: an approximation of the sensor's own encoder at firmware quality 12 |
| Output | `tests/fixtures/synthetic_video/` | `tests/fixtures/esp32cam_video/` |

Scene, marker layout, lighting and camera path are shared, so the two
fixtures differ only in what the camera is. The `phone` profile keeps
its values exactly, and its fixture is not re-rendered. The `esp32cam`
numbers are estimates, recorded in the manifest like every other
parameter, to be replaced with measurements from a real board.

The profile was first rendered at 800×600, the firmware's original
default, and failed: 80 mm markers at about 3 m came out ~18 px wide, 12
of 20 frames were extrapolated, and the aim error reached 276 mm. The same
sweep rendered at 1024×768 (25 px, max 2.9 mm), 1280×720 (31 px, 2.2 mm)
and 1600×1200 (39 px, 1.8 mm) all passed. The firmware default moved to
1024×768 — the smallest that passes, keeping the lens's full 4:3 view —
and the profile with it. Sizes above 800×600 put the OV2640 in its slower
full-array mode, so the cost is roughly half the frame rate, which only a
board can measure.

`tests/test_solve_video_e2e.py` is parametrised over both fixtures, with
tolerances per fixture. The device fixture's tolerances are set from its
first measured run and recorded with the numbers that produced them. If
the device fixture does not solve every frame, that is a finding about
the default resolution and gets reported, not tolerated away.

Rolling shutter stays unmodelled, as the generator's docstring already
states. Modelling it would mean rendering each frame as time-offset row
bands, which multiplies render time. It is a candidate follow-up once
real frames show how much it matters.

### Build in the pinned ESP-IDF image, as the invoking user

`firmware/boresight-cam/tools/idf.sh <profile> <idf.py args…>` runs
`docker run --rm` on `espressif/idf:v5.4` with the repository mounted at
`/project`, `--user $(id -u):$(id -g)` and `HOME` pointed at a writable
directory, then `idf.py` with the profile's arguments. The whole
repository is mounted, not just the firmware, because the emulator build
reads fixtures from `tests/fixtures/`. Running as the user keeps
`build/`, `managed_components/` and `dependencies.lock` deletable.

Alternatives: installing ESP-IDF on the host (what this change exists to
avoid), or Podman (works with the same flags; Docker is what is set up
here, and the script honours `CONTAINER=podman`).

### Profiles: separate build directory and configuration file

- `device`: `idf.py -B build` with the default `sdkconfig`.
- `emulator`: `idf.py -B build-emulator -D SDKCONFIG=build-emulator/sdkconfig
  -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.emulator"`.

The emulator's `sdkconfig` lives inside its gitignored build directory,
so it can never overwrite the device's (which holds Wi-Fi and token
secrets) or be committed. `sdkconfig.emulator` is tracked; it holds no
secrets because its server address, port and token are fixed test values
for a loopback-only server.

### One switch, `CONFIG_BORESIGHT_EMULATOR`, selects the substitutes

A single Kconfig bool rather than independent "fake camera" and
"Ethernet" switches: the substitutes only make sense together, and
independent switches would allow a device build with a fake camera.
`main/CMakeLists.txt` picks sources by it:

| Concern | Device | Emulator |
| --- | --- | --- |
| Network | `wifi.c` | `net_openeth.c` |
| Camera | `camera.c` | `camera_fake.c` |
| Button level | `gpio_get_level` | console-injected level |
| Console commands | — | `console.c` |

The version string sent in `hello` and logged at boot gets an
`+emulator` suffix, so a session on the server can never be mistaken for
a board. The boot configuration check skips the Wi-Fi SSID in emulator
builds.

`sdkconfig.emulator` also turns PSRAM off (not needed without real
frame buffers, and one less emulated device to depend on), sets a 4 MB
flash with `partitions_emulator.csv` (a 3 MB factory app, since the
embedded frames add about half a megabyte) and fixes the server at
`10.0.2.2:7391` with token `emulator-token`. Port 7391 rather than 7331
so a development server left running does not answer the emulator.

### Network: a neutral interface, open_eth behind it

`wifi_start`/`wifi_wait_connected` become `network_start`/
`network_wait_connected` in `boresight_cam.h`; `wifi.c` implements them
unchanged for hardware, and `net_openeth.c` implements them with
`esp_eth_mac_new_openeth` + the generic PHY + DHCP, setting the same
connected bit on `IP_EVENT_ETH_GOT_IP`. `link.c` only ever waited on
"connected", so it does not change beyond the rename.

QEMU's user-mode network gives the guest `10.0.2.15` and maps `10.0.2.2`
to the loopback of the machine QEMU runs on. QEMU runs inside the
container, so the container is started with `--network host`: its
loopback is the host's, and a server bound to `127.0.0.1` is reached
with nothing exposed. (Alternatives: a published port or a tunnel, both
of which expose a socket that moves the mouse.)

### Camera: a frame interface, fixtures behind it

`main.c` stops calling `esp_camera_fb_get` directly and uses
`camera_grab(camera_frame_t *)` / `camera_release(camera_frame_t *)`,
where a frame is a pointer, a length and an opaque handle. `camera.c`
wraps `esp_camera_fb_get`/`fb_return` in them; `camera_fake.c` returns
embedded frames in rotation and never blocks, since the capture loop
already paces to the frame-rate cap.

Frames `frame_0001`–`frame_0008.jpg` from `tests/fixtures/esp32cam_video`
are embedded with `target_add_binary_data`. CMake reads the first two
bytes of each and stops with a "run `git lfs pull`" message unless they
are `FF D8`. Eight frames, not twenty: enough to show the stream moving
and to compare positions. At 1024×768 they take well under a megabyte
of flash, and they are what the real sensor would deliver at the
firmware's default settings.

`camera_start` in the fake reports the size parsed from the first frame
by a new `bp_jpeg_dimensions()` in `boresight_proto` (walks markers to
the first SOF0/SOF1/SOF2), so the size in `hello` is read, not
hardcoded. Its host tests use a hand-built minimal JPEG header and a
real fixture file located through a compile definition.

### Buttons: inject the level, keep everything else

In emulator builds `buttons.c`'s `is_pressed()` returns a per-button
injected level instead of reading the pin, and `buttons_inject(index,
pressed)` sets it and notifies the button task — exactly what the edge
interrupt does. The debouncer, `press()`/`release()`, the session check
that suppresses a stale `up`, and the discard-while-disconnected rule
all run unmodified. GPIO configuration is kept (harmless in QEMU), so
the hardware path compiles in both builds.

`console.c` reads lines from the UART console (`stdin` through the VFS)
and understands `press`, `release` and `click` (press, wait longer than
the debounce, release). It logs each command it applies.

### Link-state changes on the console, everywhere

`status_led_set_link()` logs `state: <name>` when the state actually
changes. That is useful on a board with a serial cable too, and it gives
the emulator suite something stable to wait on rather than internal log
wording.

### Running QEMU

`tools/run-emulator.sh` merges the emulator build into a 4 MB image
(`esptool.py merge_bin --fill-flash-size 4MB @flash_args`), then runs,
inside the same container image:

    qemu-system-xtensa -nographic -machine esp32
      -drive file=flash_image.bin,if=mtd,format=raw
      -nic user,model=open_eth
      -global driver=timer.esp32.timg,property=wdt_disable,value=true
      -serial stdio

with `docker run -i --network host`. The console is the process's
stdin/stdout, which is what both a person and the test suite drive.
The watchdog property is what `idf.py qemu` also sets: the emulated
timer group watchdog otherwise fires during boot under load.

### The end-to-end suite

`tests/test_firmware_emulator.py`, marked `emulator` (registered in
`pyproject.toml`), skipped unless `BORESIGHT_EMULATOR_TESTS=1`, Docker
answers, and `build-emulator/` holds a built image — each with its own
skip reason. A module-scoped fixture starts the emulator once (boot and
DHCP take seconds); the server is a function-level fixture that can be
stopped, restarted and given a different token, running uvicorn in a
thread on `127.0.0.1:7391` with one `FakeCursorBackend` shared across
restarts so presses are counted across them. A reader thread collects
console lines; helpers wait for a pattern with a timeout.

Order within the module is deliberate: streaming, trigger hold,
disconnected press, then token refusal last, because after a refusal
the device waits 30 s before it tries again.

Positions are compared as sets: each solved position the server reports
must be one the replay of the embedded frames produces, rounded as the
wire rounds them. The drop policy makes the exact sequence timing-dependent,
which is what the existing streaming tests avoid by sending
synchronously; the device cannot.

## Risks / Trade-offs

- [The `esp32` QEMU machine's open_eth or timer behaviour differs from
  what this design expects] → the first bring-up task is a manual QEMU
  boot; the design changes before the suite is written if it does not
  hold.
- [Emulated time runs at a different speed from real time] → the suite
  asserts on events and counts, never on frame rates or latencies, and
  uses generous timeouts.
- [The emulator exercises a different network driver than the board] →
  the network module is thin and only sets "connected"; Wi-Fi
  reconnection remains a hardware task in `add-esp32-cam-firmware`.
- [First build downloads components from the registry] → cached in
  `managed_components/`; later builds are offline.
- [Compile errors in the untested firmware] → fixing them is in scope
  here, and the corresponding build tasks in `add-esp32-cam-firmware`
  are ticked once the device profile builds.

## Migration Plan

Additive. The device build is unchanged apart from the network and
camera interface renames and the state-change log line.
