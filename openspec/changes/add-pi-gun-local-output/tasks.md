# Tasks

## 1. Side-bar placement in the overlay

- [x] 1.1 `overlay.layout.bar_layout` and `overlay.render.render_layout` (written during the dropped console plan): six tags in the bars beside a centred picture, refused with the display size and needed bar width when the bars are too narrow. Verify with `tests/test_bar_layout.py`: no overlap with the picture, numbering, size, refusals, decoding where the layout says, and a solve through a known homography.
- [x] 1.2 Add `--picture-aspect W:H` to `boresight.overlay`: draw `render_layout(screen, bar_layout(...))` when given, and include the aspect in the geometry report. Verify with a unit test of the drawn canvas and the report, and that without the option the drawing and report are unchanged.
- [x] 1.3 Pass a picture aspect through `MarkerSourceController` (to the overlay command, and into the layout derived from its report), and add `overlay_picture_aspect` to the server's settings file (default unset). Verify with tests using the controller's injectable launcher: the solved layout equals `bar_layout` for the reported geometry, and an unset aspect leaves command and layout as before.

## 2. Camera sources

- [x] 2.1 Add `[camera] source` (`auto` default, `webcam`, `rpicam`, `picamera2`) and `device` (webcam index or path) to the gun config. `rpicam` refuses a width that is not a multiple of 64 or a height not a multiple of 16, naming the size and the rule. Verify with unit tests for defaults, each source, an unknown source (the error names all four) and the size rule.
- [x] 2.2 Implement the `rpicam` camera: run `rpicam-vid` with raw YUV420 to stdout and the fixed exposure, gain, white balance and denoise flags; read whole frames and keep the Y plane; drain its stderr to the log; report its last lines when it exits; stop it on close. Verify with a stand-in `rpicam-vid` on `PATH` that checks its arguments and writes known frames (the luma comes back exactly, frame after frame), one that exits early (a camera failure with its message), and one that writes a short frame.
- [x] 2.3 Implement the `webcam` camera with OpenCV: open by index or path, request size, frame rate and manual exposure and gain, log what was applied and warn when exposure stays automatic, and return greyscale frames. Verify by opening a generated video file as the device (frames come back in greyscale, in order, then end), and with a unit test of the warning against a stub capture.
- [x] 2.4 Choose the source (`auto` is `rpicam` when `rpicam-vid` is on `PATH`, else `webcam`) and open it in `__main__` for both outputs, keeping `picamera2` as `PiCamera`. Verify with unit tests of the choice, and that the existing gun tests still pass.

## 3. The gun's local output

- [x] 3.1 Add `output` (`usb` default, `local`) and an `[overlay]` section (`display`, `extra_margin_px`, `picture_aspect`) to the gun config. The local output ignores `layout` with a log line. Verify with unit tests for defaults, overrides, an unknown output (the error names `usb` and `local`) and a malformed aspect.
- [x] 3.2 Give `Gun` an optional pipeline argument (anything with the session pipeline's `process_frame`), defaulting to today's `AimPipeline` + `HoldingPipeline` over its backend. Verify that the existing recorded-frames test still yields the server's positions unchanged, and that a supplied pipeline is the one used.
- [x] 3.3 Wire the local output in `__main__`: a `UinputCursorBackend`, a `MarkerSourceController` around it switched to on-screen markers with the `[overlay]` settings, and `Gun` with the controller's session pipeline and the GPIO trigger. Stop with a failure, releasing the button, when the overlay exits. Verify with tests using a recording cursor and a stand-in overlay launcher: aim reaches the cursor, a bounced trigger is one press and one release, an overlay that exits stops the gun with the button released, and an overlay that refuses to start is reported.
- [x] 3.4 Make `--emulate FRAMES_DIR` work with the local output (stand-in overlay launcher, recording cursor, `--screen WxH`) and run it in the tests. Verify that the printed cursor positions equal the pipeline's aim for the frames against the reported layout, and that `uv run pytest`, `ruff check` and `ruff format --check` pass.
- [x] 3.5 Add `--autostart` and `--autostart remove`: write or delete `~/.config/autostart/boresight-gun.desktop`, which runs this program with this config and restarts it after a failure but not after a clean exit. Verify with tests against a temporary `XDG_CONFIG_HOME`: the entry's contents, removing it, and the `Exec` line run under `sh` against a stand-in program that fails twice then succeeds (it runs three times and stops).

## 4. Packaging and documentation

- [x] 4.1 Add `gun` (`gpiozero`, `lgpio`) and `local` (`evdev`, `PySide6-Essentials`, `pydantic`) extras to `pyproject.toml`. Verify that `uv lock` resolves and that the core-only install test still imports the pipeline without them.
- [x] 4.2 Strip `deploy/pi/install.sh` to the `usb` output's root setup: the dwc2 overlay line, the gadget script and the system units, with no `apt-get`, `pip` or other package installation. Point the service at the checkout's `.venv/bin/boresight-gun`, and stop with a pointer to `uv sync` when it is missing. Verify with `shellcheck`, `systemd-analyze verify`, and a test that no script under `deploy/` calls a package manager.
- [x] 4.3 Rewrite `deploy/pi/README.md` around the normal install: clone, `uv sync --extra gun` (and `--extra local`), `uv run boresight-gun`. Add a "System dependencies (install yourself)" list per output and camera source, the `usb` setup script, and a "Next to an emulator" section (`output = "local"`, `--autostart`, windowed or borderless full screen, the mouse as light gun, `picture_aspect`, "Just scan", `extra_margin_px`, and a hardware checklist; no emulator named). Also cover removing an older `/opt/boresight` install, and the camera sources in the main README. Verify the links resolve and `openspec validate add-pi-gun-local-output --strict` passes.

## 5. USB gun on a Pi Zero 2 W (moved from add-pi-zero-usb-gun)

- [ ] 5.1 Follow `deploy/pi/README.md` on a fresh SD card (Raspberry Pi OS Trixie 64-bit, camera enabled, button and LED wired). Fix every step that does not work as written, and verify the guide gets a working gun with no extra steps.
- [ ] 5.2 Check the `rpicam` camera on a CSI camera: its flags are accepted, frames arrive at the configured rate, and exposure, gain and white balance stay fixed. Record fps and solve rate at 640×480 and 1024×768 in `deploy/pi/README.md`.
- [ ] 5.3 Check the gpiozero trigger and LED on the default pins (GPIO 17, GPIO 27): one press is one button down and one up on the host, and the LED shows starting, searching and aiming.
- [ ] 5.4 Check the USB gadget: a PC enumerates "Boresight light gun" as a mouse with no driver. Record the hosts tried in the README.
- [ ] 5.5 Check boot and replug: after a power cycle the gun aims with no login, and unplugging and replugging the cable brings the mouse back without a Pi reboot. Record both in the README checklist.

## 6. Local output on a Pi Zero 2 W with a TV

- [ ] 6.1 On the Desktop image, check that the overlay stays above an emulator running windowed or borderless full screen under labwc. If it does not, move the overlay to its layer-shell path, and record the outcome in design.md and the README.
- [ ] 6.2 With `output = "local"` and `--autostart`, log in, and confirm the overlay appears and the cursor follows the gun with no command.
- [ ] 6.3 Play a light-gun game in an emulator of your choice, from a ROM you own. Verify that hits land where aimed across the picture, and that the trigger fires once per pull.
- [ ] 6.4 Measure with the emulator running: its frame rate, tracking fps and solve rate, CPU per core and SoC temperature. Record them in the README, and lower the camera resolution if the emulator drops frames.
- [ ] 6.5 On a TV with overscan on and then off, check that all six tags are detected. Find the `extra_margin_px` that overscan needs, and record both in the README.

## Workflow follow-up

- Archive this change once the hardware tasks in groups 5 and 6 are done, then verify the archived specs.
