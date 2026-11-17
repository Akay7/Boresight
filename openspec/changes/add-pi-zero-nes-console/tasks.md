# Tasks

## 1. Geometry: viewport and bar layout

- [ ] 1.1 Add the single viewport function (output size and NES pixel aspect → centred game rectangle). Verify with unit tests at 1280×720, 1920×1080 and 1024×768 that it fills the height, keeps 8:7 and is centred to the pixel.
- [ ] 1.2 Add `bar_layout(output_px, viewport, margin_px)` next to `overlay_layout`: six tags (0–3 in the bar corners, 7 and 5 at the bar middles), sized to the bar with the quiet-zone patch. It raises, naming the resolution and minimum bar width, when the tags would fall below the minimum size. Verify with unit tests that no tag or patch overlaps the viewport at any accepted size, that the numbering matches the printed layout, and that the narrow-bar case raises.
- [ ] 1.3 Verify that the `MarkerMap` from `bar_layout` solves: a unit test projects the six tags through a known homography, and `AimPipeline` recovers the expected aim at the centre and corners of the viewport.

## 2. Emulator core binding

- [ ] 2.1 On a PC with `libretro-nestopia`, check by hand with a ROM you own: the core option that puts a Zapper on port 2, the lightgun coordinate range and off-screen flag it reads, and the region and frame rate it reports. Record the findings in design.md under "Nestopia UE from apt". If they differ from the design, update the design before continuing.
- [ ] 2.2 Define the core interface (load ROM, run one frame, video/audio/input callbacks, core options, controller port devices, region). Implement the ctypes libretro wrapper for it. Verify with a test that builds a small C stub core (skipped when no C compiler) and checks: pixel-format negotiation, a frame callback with known pixels, an audio batch, input polls on ports 1 and 2, and clean unload.
- [ ] 2.3 Implement the pure-Python stand-in core: it draws a known frame, emits a tone and records every lightgun and joypad poll. Verify with a unit test that it satisfies the same interface tests as the stub.

## 3. Aim, Zapper and buttons

- [ ] 3.1 Add the shared aim record (x, y, solved, time) and a tracker cursor backend that writes it. Verify with a unit test that a reader in another process sees the latest write and never a torn record.
- [ ] 3.2 Implement the aim→Zapper mapping: output pixels, minus the viewport origin, scaled to the core's lightgun range. Off-screen when outside the viewport, with no aim, or after the aim-hold time. Verify with unit tests for picture centre and corners, each bar, outside the screen, a stale aim and no aim.
- [ ] 3.3 Add optional `start`/`select` pins to `[pins]`, debounced like the trigger and validated with all other pins. Verify with unit tests for bounce, an absent pin and a clash with the trigger or LED (the error names both pins).
- [ ] 3.4 Map the trigger, Start, Select and an SDL GameController to the core's port-1 joypad and port-2 Zapper. Each game frame samples them together with the aim. Verify with a stand-in-core test: one bounced trigger pull gives exactly one Zapper pull, and Start and Select reach port 1.

## 4. Display, audio and pacing

- [ ] 4.1 Implement the SDL2 renderer: the NES frame texture scaled nearest-neighbour into the viewport, and a bars texture rendered once from `bar_layout` (tags on opaque patches). It has a software-render fallback flag. Verify with an off-screen test: render a composed frame with the stand-in core, run the existing detector on it, find all six tags at their layout positions and none inside the viewport, including on a black game frame.
- [ ] 4.2 Implement the no-ROM screen: the bars plus a centred message naming the problem. Verify with the off-screen test that the tags are found and the message is drawn.
- [ ] 4.3 Implement audio through an SDL queue with dynamic rate control (±0.5 %, targeting ~3 frames). Verify with a unit test that feeds a source 0.16 % fast or slow: the queue level stays bounded over 10 simulated minutes.
- [ ] 4.4 Implement the frame loop: one `retro_run` per vsync, the output refresh matched to the game's region when the mode exists, and a per-interval frame-time histogram and late-frame count in the log. Verify with a test against the stand-in core and an off-screen clock that it runs one frame per tick and reports late frames.

## 5. The console program

- [ ] 5.1 Extend `boresight.gun` config: `mode` (`usb` default, `console`), and `[console]` with `rom`, `resolution`, `margin_px`, `core` and `software_render`. Console mode ignores `layout` with a log line. Verify with unit tests for defaults, each override, an unknown mode (the error names `usb` and `console`) and a malformed resolution.
- [ ] 5.2 Run console mode as two processes: the game process (pinned to core 0, higher priority) and a tracker child (cores 1–3) that gets the parent's `bar_layout` `MarkerMap` and writes the aim record. Stopping either stops both and releases the Zapper. Verify with an emulated test that a killed tracker ends the game process cleanly, and that the Zapper reads off-screen afterwards.
- [ ] 5.3 Implement ROM selection: a file, or a folder in name order. Holding Select for 1 s at startup advances it, and the choice is kept in the state directory. A missing or broken ROM falls back to the no-ROM screen. Verify with unit tests for each case, including persistence across two runs.
- [ ] 5.4 Implement the throttle monitor: read the throttle flags every 5 s from sysfs, or else `vcgencmd`. Log each new under-voltage or throttling condition once, with its advice, and show the LED error pattern while under-voltage is present. Verify with unit tests against injected flag values.
- [ ] 5.5 Make `--emulate` support console mode: recorded frames, injected buttons, the stand-in core and an off-screen display. Add it to the test suite and CI. Verify that the stand-in core's recorded Zapper positions equal the frames' known aim mapped to NES pixels, and that `uv run pytest`, `ruff check` and `ruff format --check` pass.

## 6. Deployment and documentation

- [ ] 6.1 Add `--mode usb|console` to `install.sh`. Console mode installs `libretro-nestopia` and `python3-sdl2`, writes `dtoverlay=dwc2,dr_mode=host`, sets `multi-user.target` and disables the gadget service. USB mode restores `peripheral` and the gadget. The gun service gets `StateDirectory=boresight` and access to `/dev/dri` and audio. The gun warns when `mode` and the USB role disagree. Verify with `shellcheck`, `systemd-analyze verify` and a unit test for the mismatch warning.
- [ ] 6.2 Add a console section to `deploy/pi/README.md` covering the HDMI cable, the 5 V 2.5 A supply, the heatsink, the Start/Select wiring, ROM placement (no ROMs supplied), TV "Just scan", `margin_px`, switching modes, and a hardware checklist. Point to it from the main README. Verify the links resolve and that `openspec validate add-pi-zero-nes-console --strict` passes.

## 7. USB gun on a Pi Zero 2 W (moved from add-pi-zero-usb-gun)

- [ ] 7.1 Follow `deploy/pi/README.md` on a fresh SD card (Raspberry Pi OS Trixie 64-bit, camera enabled, button and LED wired, `install.sh`). Fix every step that does not work as written, and verify the guide gets a working gun with no extra steps.
- [ ] 7.2 Check the picamera2 camera: luma frames, fixed exposure and gain, AWB off, sensor timestamps, and its applied settings in the log. Record fps and solve rate at 640×480 and 1024×768 in `deploy/pi/README.md`.
- [ ] 7.3 Check the gpiozero trigger and LED on the default pins (GPIO 17, GPIO 27). Verify that one press gives one button down and one up on the host, and that the LED shows starting, searching and aiming.
- [ ] 7.4 Check the USB gadget: a PC enumerates "Boresight light gun" as a mouse with no driver. Record the hosts tried in the README.
- [ ] 7.5 Check boot and replug: after a power cycle, the gun aims with no login. Unplugging and replugging the cable brings the mouse back without a Pi reboot. Record both in the README checklist.

## 8. Console on a Pi Zero 2 W with a TV

- [ ] 8.1 Measure at 720p while playing: game frame-time histogram and late frames, tracking fps, solve rate and drops, CPU per core, RAM, SoC temperature with and without a heatsink, and current at 5 V. Record them in design.md's Budget table and in the console README. If the game drops frames, switch to FCEUmm or lower the camera resolution, and record the choice.
- [ ] 8.2 Play a Zapper game from your own ROM. Verify that hits land where aimed across the picture, that shooting the bars or off the TV misses, and that Start and Select work from the GPIO buttons and from a USB gamepad.
- [ ] 8.3 On a TV with overscan on and then off, check that all six tags are detected. Find the `margin_px` that overscan needs, and record both in the README.
- [ ] 8.4 Power-cycle the gun with no login and confirm it boots into the configured game. Run it from a TV's USB port and confirm the under-voltage warning appears. Record the results in the README checklist.

## Workflow follow-up

- Archive this change once the hardware tasks in groups 7 and 8 are done, then verify the archived `gun-console` spec.
