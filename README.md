# Boresight

A computer-vision light gun. Printed fiducial markers around the display,
an Android phone as the barrel camera, absolute mouse output injected
straight into the OS.

The phone just streams video and renders an on-screen trigger button in
a browser tab, over Wi-Fi to a small web server on the PC. All detection
and solving runs on the PC — no firmware, no wiring, no pairing beyond
joining the same network.

Works with NES emulators, MAME, and anything with mouse aim.

## Why

The original NES Zapper worked by CRT raster timing — the console flashed
a white rectangle and the gun's phototransistor reported whether it saw
the beam. LCDs have no raster, so that method is dead.

Commercial replacements use IR emitters (Wii-style) or a white screen
border (Sinden-style). Boresight uses printed ArUco markers instead:
no wiring, no power supply at the TV, no screen real estate consumed,
and full perspective correction from a single visible tag.

## How it works

1. Markers with known IDs sit at known positions around the bezel.
2. The phone's camera sees some subset of them and streams frames to the PC.
3. Each visible marker contributes 4 point correspondences.
4. Solve a homography from image plane to screen plane.
5. Push the image centre through the inverse — that's the aim point.
6. Filter, then emit as an absolute mouse position.
7. A tap on the phone's on-screen trigger button rides the same
   connection and is emitted as a click.

One marker is sufficient. Four corner points is a complete homography.
More markers improve accuracy and provide redundancy.

## Hardware

| Part | Notes |
| --- | --- |
| Android phone | Any phone with a modern browser and a rear camera. Doubles as the trigger — no dedicated webcam module or microcontroller needed |
| NES Zapper shell | Gut the phototransistor board. Houses/mounts the phone instead of a camera PCB; the trigger microswitch goes unused since the trigger is on-screen |
| Matte cardstock | Marker substrate. Never glossy |

Phone cameras auto-expose aggressively and hit the same dynamic-range
problem as any other sensor here — pin exposure via the browser's
`MediaTrackConstraints` where the device/browser exposes that control.

### Future: dedicated hardware path

Camera and trigger don't have to be a phone — see
[Future work](#future-work) for the ESP32-CAM / ESP32-S3 hardware path.
Rolling shutter is workable at short exposure; a global-shutter camera
module trades cost for less motion blur if the stock OV2640 isn't
enough.

## Marker system

Dictionary: `DICT_4X4_50`. Fewest bits per cell means largest cells for a
given paper size, which is what governs detection range. AprilTag 36h11
detects more reliably but needs a physically larger tag for equal range.

Layout: 8 tags minimum — 4 corners plus 4 edge midpoints. Midpoints matter
because a narrow-FOV camera at close range will not see the corners.
Consider a second inner ring for very close play on large displays.

Each position gets a distinct ID. This resolves orientation ambiguity and
lets the solver identify partial views.

### Sizing

Decode needs roughly 3 px per cell. A 4x4 ArUco is a 6x6 grid including
its quiet border, so ~20 px across the tag, minimum.

| Distance | FOV | Resolution | Min tag size |
| --- | --- | --- | --- |
| 3 m | 60 deg | 640x480 | ~110 mm |
| 3 m | 60 deg | 1280x720 | ~55 mm |
| 3 m | 30 deg | 1280x720 | ~28 mm |

Narrower optics buy more than higher resolution. The tradeoff is that a
narrow FOV loses tags at close range — hence the midpoint ring.

Print at 100% scale. Never "fit to page".

## Pipeline

    grayscale
      -> adaptive threshold
      -> contours
      -> quad approximation
      -> perspective unwarp to canonical square
      -> Otsu
      -> bit extraction
      -> dictionary match, 4 rotations, Hamming tolerance
      -> cornerSubPix refinement
      -> undistortPoints (intrinsics from one-time calibration)
      -> findHomography, RANSAC, all correspondences
      -> invert, map image centre to screen space
      -> 1-euro filter
      -> emit

`cv::aruco::ArucoDetector` covers detection through dictionary match.

Two steps that are easy to skip and shouldn't be:

**cornerSubPix.** Integer-precision corners produce a cursor that
vibrates 15-20 screen pixels at rest. Subpixel refinement takes it to 2-3.

**undistortPoints, not undistort.** Cheap wide lenses have real barrel
distortion, but only ~32 corner coordinates matter. Undistorting those is
microseconds; undistorting 300k pixels per frame is not.

## Known failure modes

**Exposure.** The dominant problem. Paper next to a bright screen in a dim
room is a severe dynamic range case — auto-exposure chases the screen and
the tags underexpose to mud. Lock exposure manually and low. Keep some
ambient light on the bezel. Matte substrate only; gloss catches screen
glare and blows out a quadrant of the tag.

**Motion blur.** Shutter speed matters more than framerate. Fast swings
smear the quads until contour detection fails. Short exposure needs light,
which fights the exposure fix above.

**Dropout.** Detection will fail for a few frames mid-swing. Never let the
cursor jump — hold the last good pose and decay. Gyro integration (future
hardware path) covers gaps of ~100 ms cleanly where available. Vision
always remains the authority; an IMU only fills gaps.

**Network.** Wi-Fi adds latency and occasional frame loss a wired camera
didn't have, plus the browser's own capture/encode overhead. Measure
round-trip time before tuning anything else — a dedicated 5 GHz link (or
tethering the phone to the PC as a USB network device) is the first fix
if jitter is unacceptable.

## Software stack

| Layer | Choice |
| --- | --- |
| Detection | OpenCV 4.7+, `objdetect` module (ArUco moved out of contrib in 4.7) |
| Prototype language | Python 3.14 + numpy |
| Production language | C++20, CMake, vcpkg |
| Package manager | `uv` |
| Web server | FastAPI (Python); serves the phone client and the video/trigger RPC endpoint |
| Phone client | Static HTML/JS page: `getUserMedia` capture + on-screen trigger button, no native app |
| Transport | WebSocket (or WebRTC if `getUserMedia`-over-WebSocket latency proves too high) |
| Filtering | 1-euro filter, hand-rolled (~30 lines) |
| Marker generation | `generateImageMarker` -> SVG -> PDF |
| Calibration | `calibrateCamera`, chessboard target |
| Firmware | None required for v1. Future hardware path, independently optional: a Wi-Fi camera (mirrors the phone architecture) needs an ESP32 with a camera interface (e.g. ESP32-CAM); a wired native-USB HID trigger needs an ESP32-S3 (TinyUSB) — the plain ESP32 in ESP32-CAM has no native USB. A camera-equipped ESP32-S3 board (e.g. XIAO ESP32S3 Sense) does both on one chip |
| Config | TOML |
| Testing | `pytest` |
| Code quality | `ruff` (lint + format) + `pre-commit`, enforced at commit time |

Detection runs ~3-6 ms at 640x480 in C++. Python adds 1-2 ms of overhead,
which is acceptable for v1. Network hop time is on top of that and is the
new dominant latency term versus the old wired-webcam path.

Pin exposure manually wherever the platform allows it — browser
`MediaTrackConstraints` on the phone path, `CAP_PROP_AUTO_EXPOSURE` on the
future wired path. This single setting determines whether the project
works, on either path.

## Cursor injection

**Trigger.** The phone's page renders a trigger button; a tap sends an
event over the same WebSocket connection the video arrives on. The
PC-side handler fires a synthetic mouse-down/up alongside the current aim
point — no separate USB HID device needed for v1.

Two paths for the aim coordinate, selectable by config flag.

**Direct injection.** Windows `SendInput` with
`MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE`, or a uinput virtual absolute
pointer on Linux. Zero added latency, trivial to implement, works with
emulators. Some fullscreen-exclusive titles ignore synthetic events.

**Hardware round-trip (future).** PC computes the coordinate, sends it
over serial to an ESP32-S3 (native USB), which emits the absolute HID
report. Costs 2-4 ms, but the OS sees a genuine USB pointing device that
nothing can distinguish from real hardware. Not needed for the
phone-based v1; see [Future work](#future-work).

Build direct first. The homography code is agnostic to the consumer.

HID descriptor note: X and Y must use `Input (Data, Var, Abs)` with
logical min 0, max 32767, 16-bit fields. The Abs flag is the entire
difference between a pointer that jumps to where you aim and one that
nudges from wherever the cursor happens to be.

## Running the server (current slice)

What exists today is the smallest possible proof that the injection
primitive works: a FastAPI server with one endpoint,
`POST /cursor/move`, that takes normalized `{"x": 0.0-1.0, "y": 0.0-1.0}`
and moves the real OS cursor via a Linux `uinput` virtual absolute
pointer. No video or trigger handling yet, and homography solving
(`solve.py`) exists but isn't wired into the server — see "Homography
solving (standalone)" below.

**Setup**

    uv sync
    uv run pre-commit install

The second command is one-time per clone: it wires up `ruff` (lint +
format) and a few hygiene checks as a git commit hook, so violations are
caught before they land instead of drifting in silently. Run the same
checks on demand (e.g. in CI) with:

    uv run pre-commit run --all-files

**`/dev/uinput` permission.** The server needs read/write access to
`/dev/uinput`, which is root-only by default on most distros. Grant it
via udev instead of running the server as root:

    # /etc/udev/rules.d/60-uinput.rules
    KERNEL=="uinput", GROUP="input", MODE="0660"

then add your user to the `input` group (`sudo usermod -aG input $USER`,
then re-login) and reload udev rules
(`sudo udevadm control --reload-rules && sudo udevadm trigger`).

**Run**

    uv run python -m boresight.server

Binds to `127.0.0.1:8000` only — fine for now since the only client is
`curl` on the same machine. This will need to change once the phone is
actually in the loop: a phone on Wi-Fi is a separate device and can't
reach loopback at all, so that future work needs both a LAN-reachable
bind address and a real auth story before it's safe to open up. Move the
cursor to screen center:

    curl -X POST http://127.0.0.1:8000/cursor/move \
      -H 'Content-Type: application/json' \
      -d '{"x": 0.5, "y": 0.5}'

**Test**

    uv run pytest

The suite runs entirely against a fake backend and never touches
`/dev/uinput`.

## Homography solving (standalone)

`solve.py` implements the Pipeline section's homography step: given
marker correspondences (a known screen-plane position in mm paired with
a detected image-plane position in px), it solves `findHomography`
(RANSAC, all correspondences), inverts it, and maps the image centre
through the inverse to get the screen-space aim point. It takes plain
correspondence data — no config file or detector call of its own — so
it composes with whatever produces those correspondences.

There's no camera or video source yet — markers aren't even printed
(see Milestones) — so it's tested entirely with synthetic data, in
increasingly realistic stages: pure synthetic geometry (a known
ground-truth homography generates synthetic correspondences directly,
`tests/test_solve.py`); a synthetic rendered image (ArUco markers drawn
onto a canvas and warped by a known homography, run through the real
detector in `detect.py`, then through `solve.py`,
`tests/test_solve_synthetic_image.py`); and that same rendered image
degraded with the failure modes the "Known failure modes" section below
names as dominant in practice — uneven exposure, blur, sensor noise —
run through the full detect-then-solve pipeline end to end
(`tests/test_solve_e2e_realistic.py`), the closest available
approximation to "solve.py against a real photo" until an actual camera
exists. All three assert the recovered aim point against the known
ground truth within a documented tolerance. Run them with the same
`uv run pytest` as the rest of the suite.

The third stage's photo is checked in, not regenerated per test run —
`tests/fixtures/synthetic_photo.png` plus its ground-truth metadata,
`tests/fixtures/synthetic_photo.json` — so it's a real regression test:
a `detect.py`/`solve.py` change that alters the result against this
exact image is a signal worth investigating, not noise from a
re-rolled random seed. Regenerate it (only for a deliberate change to
the layout or degradation model) with:

    uv run python tests/generate_synthetic_photo_fixture.py

### Synthetic video (per-frame behaviour)

A stateless solver can be right on every frame in isolation and still
produce a trajectory that jitters, because each frame's homography is
fitted independently. `tests/test_solve_video_e2e.py` covers that:
it runs the whole `detect.py` → `solve.py` pipeline over a checked-in
frame sequence and asserts both per-frame accuracy and that
consecutive-frame aim points track the known consecutive-frame camera
motion — no discontinuities the input motion doesn't justify.

The fixture is a Blender render (`tests/fixtures/synthetic_video/`): a
lit, colourful 16:9 panel, markers printed on white cardstock stuck to
the bezel *outside* the active area (hence their negative `markers.toml`
coordinates), and a dim room behind — deliberately the bright-screen /
dim-paper dynamic range case "Known failure modes" calls dominant.
Frames are JPEG, which is what the phone will actually stream.

Blender buys one thing a warped 2D canvas can't: each frame's
ground-truth aim point is computed from the rendering camera's own pose
— where its optical axis meets the panel plane — with no homography
involved. So the test checks `solve.py` against an independent
reference rather than against its own arithmetic. `scene.blend` is
checked in alongside the frames so the scene can be opened and
inspected rather than only re-derived from a script.

Regenerating needs Blender (`blender-5.2`; override with
`$BORESIGHT_BLENDER`). Running the tests does not — Blender is not a
project dependency:

    uv run python -m tests.generate_synthetic_video_fixture

`detect.py` currently wraps `cv2.aruco.ArucoDetector` only — dictionary
match and corner extraction, no cornerSubPix refinement or
undistortPoints yet (those are separate Pipeline steps, still future
work). Per-frame behaviour over a synthetic frame sequence is covered
below; what's still missing is a real video source, 1-euro filtering,
and any wiring into `server.py`.

## Repo layout

Target layout for the full pipeline — most of this doesn't exist yet.
Today there's `src/boresight/{server,inject,solve,detect}.py` and
`tests/`; see "Running the server" and "Homography solving (standalone)"
above for what's actually built.

    boresight/
      pyproject.toml
      config/
        markers.toml          # id -> (x, y) in screen mm
        camera.toml           # intrinsics + distortion
      src/boresight/
        server.py             # WebSocket/RPC endpoint, serves web/ to the phone
        detect.py             # ArUco detection + subpixel refinement
        solve.py              # homography, RANSAC, aim point
        filter.py             # 1-euro
        inject.py             # SendInput / uinput backends
        serial_link.py        # optional ESP32 HID path (future)
        debug_overlay.py      # quads, IDs, reprojection error
      web/
        index.html             # phone client: video capture + trigger button
        capture.js              # getUserMedia, encode, WebSocket send
      tools/
        gen_markers.py        # SVG/PDF at physical dimensions
        calibrate.py          # chessboard intrinsics
        map_markers.py        # build markers.toml
      firmware/
        boresight-hid/        # future: ESP32-S3, TinyUSB hardware path
      tests/
        fixtures/             # recorded capture clips
        test_detection.py

### markers.toml

    screen_width_mm = 1220
    screen_height_mm = 686

    [[marker]]
    id = 0
    x = -60
    y = -60
    size_mm = 80

    [[marker]]
    id = 1
    x = 610
    y = -60
    size_mm = 80

Origin is the top-left of the active display area. Negative coordinates
mean the tag sits on the bezel outside the panel.

## Milestones

- [ ] Generate and print markers at verified physical size
- [ ] Camera intrinsic calibration (phone camera)
- [ ] Web server: phone connects over Wi-Fi, streams video, PC decodes frames
- [ ] Detection on a tripod against streamed frames, print raw marker IDs and corners
- [ ] Marker map calibration tool
- [x] Homography solve, print screen coordinates: `solve.py` implements
      `findHomography` + RANSAC + inverse-mapped aim point, tested
      against synthetic correspondences, a synthetic rendered image, and
      a Blender-rendered frame sequence covering per-frame accuracy and
      frame-to-frame coherence (see "Homography solving (standalone)") —
      built ahead of the pipeline above, like cursor injection; not yet
      wired to a real video/detection source
- [ ] Debug overlay with per-frame reprojection error
- [ ] 1-euro filter tuning
- [x] Cursor injection scaffolding: FastAPI endpoint moves the OS cursor
      directly (uinput, Linux) — built ahead of the pipeline above as a
      standalone proof; not yet wired to real aim data or Mesen
- [ ] SendInput injection (Windows), test in Mesen
- [ ] On-screen trigger button wired to click injection
- [ ] Integrate phone mount into shell
- [ ] Wi-Fi latency/jitter measurement and tuning
- [ ] (Future) ESP32 hardware HID round-trip path
- [ ] (Future) IMU dropout bridging
- [ ] (Future) Recoil solenoid

Debug optics on the bench. Do not seal anything into the gun until the
detection loop is trustworthy.

## Testing

This is about testing the future detection pipeline once it exists; for
the current server-side pytest suite, see "Running the server" above.

Record 30 seconds through the barrel camera covering fast swings, close
range, extreme off-axis, partial occlusion, and low ambient light. That
clip is the test fixture.

Detector tuning is full of changes that improve one condition and quietly
wreck another. Replaying a fixed capture turns "it feels worse now" into a
detection-rate number. pytest with a rate assertion per condition is
enough.

## Future work

**Dedicated hardware path.** Two independent, separately optional
upgrades — not a pair you need together. An ESP32-CAM can replace the
phone as the barrel camera, streaming to the same web server over Wi-Fi
with no separate USB webcam module — dedicated hardware in the same
architecture, instead of a borrowed phone. Separately, an ESP32-S3 with
native USB HID is the option for a genuinely wired, lower-latency
trigger and injection path, and the natural home for IMU dropout
bridging (MPU6050/BNO085) and a recoil solenoid — the plain ESP32 in
ESP32-CAM has no native USB, so it can't do this job itself. A
camera-equipped ESP32-S3 board (e.g. XIAO ESP32S3 Sense) does both on
one chip, if you want both upgrades at once. Sits behind the same
`inject.py` / `serial_link.py` interface, selectable by config flag
alongside the phone path.

**On-screen markers.** Render the tags as a thin border overlay instead of
printing them. They become emissive, so the exposure problem disappears,
and their positions are known exactly in screen pixels, so calibration
disappears too. Costs a few percent of screen area and requires a
compositing layer. This is the Sinden approach with ArUco instead of a
white frame.

**Multi-gun.** Marker detection is per-camera and stateless, so two guns
need no coordination beyond distinct WebSocket connections and device IDs.

## Notes

"NES", "Zapper", and "Duck Hunt" are Nintendo trademarks. This project is
not affiliated with or endorsed by Nintendo. Compatibility with emulators
is described factually; no trademarked terms appear in the project name,
branding, or any distributed artifact.

## License

MIT
