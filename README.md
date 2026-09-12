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

One marker is enough to *compute* a homography — four corner points is
a complete one — but not enough to compute a useful aim point. What
governs accuracy is whether the visible markers enclose the aim point,
not how many of them there are. See
[Marker visibility and accuracy](#marker-visibility-and-accuracy) for
the measured numbers; the short version is that extrapolating from a
single 80mm marker has been measured 2m off on a 1220mm panel, while
any subset that surrounds the aim point stays within ~18mm.

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

Each position gets a distinct ID, which is what lets the solver identify
a partial view: it knows *which* markers it is looking at, not merely
how many.

### Attaching them

Two mistakes here are silent, so the printable sheet at `GET /markers`
carries the answers on the page — a diagram of which ID goes where, a
position label under every tag, and a `▲ TOP` mark above it.

**IDs are positions, not decoration.** `markers.toml` maps each ID to a
physical location. Swap two tags without changing the file and the
solver receives a permuted but perfectly self-consistent set of
correspondences, fits a homography to it happily, and aims somewhere
else. Nothing reports an error.

**Attach them upright.** ArUco reads a tag's rotation from its own bit
pattern, so a tag stuck on sideways is still *recognised* — but the
detector then reports its corners starting from a physical corner you
did not intend, and they pair with the wrong screen coordinates. Cost
measured by mutation: permuting every marker's corners costs 1.77mm
with all eight in view, because RANSAC averages it away across 32
correspondences, but approaches a full marker's width when only one or
two are visible. **The fewer tags you rely on, the more orientation
matters.**

The default reference layout:

           0 ──── 4 ──── 1
           │              │
           7    screen    5
           │              │
           3 ──── 6 ──── 2

Corners 0–3 clockwise from top-left, then midpoints 4–7 clockwise from
top. Nothing in the code requires this particular assignment — the
config file is the source of truth, and the sheet's labels are derived
from it, so a layout of your own relabels the printout automatically.

Cut on the dashed line, not around the tag: the white margin is the
quiet zone the detector needs to find the tag's edge at all.

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

### Marker visibility and accuracy

All markers sit on the bezel, outside the active panel. That has a
consequence worth knowing before building the mount: **there is a
minimum working distance**, and below it the system cannot work at all.
Rendering the reference scene (1220x686mm panel, 80mm tags, 45 deg FOV,
1280x720) from a range of distances while aiming at screen centre:

| Camera distance | Markers detected | Aim error |
| --- | --- | --- |
| 700 / 1000 / 1400 mm | 0 | nothing to solve from |
| 1800 mm | 2 | 0.8 mm |
| 2200 mm and beyond | 8 | 1.0-1.6 mm |

Close in, the frustum is narrower than the panel, so every bezel marker
falls outside it. No solver change fixes this — it is the case README's
"second inner ring for very close play" note is for.

When only *some* markers are visible, accuracy is governed by their
geometry relative to the aim point, not by their count. Sweeping every
marker subset across every frame of the rendered fixture (4844
combinations):

| Correspondences used | Aim error |
| --- | --- |
| all 7-8 markers | 1.4 mm median |
| 4 corners (half the layout) | 1.5 mm median, 2.0 mm max |
| 2 markers, opposite sides | 0.8 mm |
| 2 markers, same edge | 17.6 mm median, 39.5 mm max |
| 1 marker | 153 mm median, up to 2037 mm |

Two markers on opposite sides beat two markers sharing an edge by ~20x.
The reason is extrapolation: the homography is fitted from the marker
corners, and pushing the image centre through it is interpolation only
while the aim point lies inside those corners. Outside them, sub-pixel
corner error is amplified without bound — and one 80mm marker spans
80mm of a screen that is 1220mm across.

So `solve.py` reports the conditioning of each solve: whether the aim
point falls inside the convex hull of the correspondences, how far
outside it is in mm, and their extent. Across all 4844 combinations,
every solve whose aim point was *inside* the hull landed within 18.3mm,
while flagged solves ranged up to 2037mm. Being flagged does not mean
the answer is wrong — close-range frames with one visible marker still
land within a few mm, because a nearer marker occupies more pixels and
localises better — it means the answer is unguaranteed.

**Do not use reprojection error as a validity check.** A single marker
gives four points and eight degrees of freedom, so it fits *exactly*:
reprojection error is ~0.000px precisely when the aim point is least
trustworthy, and the all-markers solve has the highest reprojection
error and the best accuracy. It is anti-correlated with accuracy in the
case that matters.

The real fix for sparse visibility is pose estimation from a marker of
known physical size (`solvePnP`) rather than homography extrapolation,
which turns four coplanar points into a metric pose. That needs camera
intrinsics, so it is blocked on the calibration milestone.

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

The server does three things: serves the phone client, receives its
camera frames over a WebSocket and drives them through the pipeline to
the OS cursor, and exposes `POST /cursor/move` (normalized
`{"x": 0.0-1.0, "y": 0.0-1.0}`) plus the printable marker sheets. The
trigger is not wired yet — see Milestones.

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

Binds to `127.0.0.1:7331` only — fine for now since the only client is
`curl` on the same machine. This will need to change once the phone is
actually in the loop: a phone on Wi-Fi is a separate device and can't
reach loopback at all. Serving one means binding an address the LAN can
route to — see "The phone client" below, which is also where the token
comes in. Move the cursor to screen center:

    curl -X POST http://127.0.0.1:7331/cursor/move \
      -H 'Content-Type: application/json' \
      -d '{"x": 0.5, "y": 0.5}'

**Test**

    uv run pytest

The suite runs entirely against a fake backend and never touches
`/dev/uinput`. It exercises the WebSocket path too, by replaying the
checked-in fixtures through it — Starlette's test client drives the ASGI
app directly, so no socket is opened and no camera is involved.

## Homography solving (standalone)

`solve.py` implements the Pipeline section's homography step: given
marker correspondences (a known screen-plane position in mm paired with
a detected image-plane position in px), it solves `findHomography`
(RANSAC, all correspondences), inverts it, and maps the image centre
through the inverse to get the screen-space aim point. It takes plain
correspondence data — no config file or detector call of its own — so
it composes with whatever produces those correspondences. Alongside the
aim point it reports the solve's conditioning (see
[Marker visibility and accuracy](#marker-visibility-and-accuracy)); it
never refuses on conditioning grounds, because what to do about a
low-confidence aim point — README's hold-last-good-pose-and-decay — is
the consumer's call.

Its tests are organised as two decks, which assert different things:

- **Deck A, full visibility** — the whole layout in frame
  (`test_solve_synthetic_image.py`, `test_solve_e2e_realistic.py`,
  `test_solve_video_e2e.py`). Tight tolerances; this is the statement
  of best-case accuracy.
- **Deck B, partial visibility** — only some markers in frame
  (`test_solve_partial_markers.py`, `test_solve_close_range.py`). Where
  the geometry supports accuracy it asserts accuracy; where it does not
  it asserts the solve is *flagged*, since no solver can recover an
  accurate aim point by extrapolating far outside its own
  correspondences.

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
coordinates), and a dim room behind. Frames are JPEG, which is what the
phone will actually stream.

The lighting is real, not painted on. The panel is the only emitter;
the bezel, cardstock and room are Principled BSDF surfaces lit by area
lamps, rendered in Cycles, with a roughness map separating matte
cardstock from the semi-gloss bezel. So the bright-screen / dim-paper
dynamic range case above is an optical consequence — real falloff
across the marker layout, real spill from the screen onto the paper,
real blown highlights — rather than a brightness constant per surface.
Cycles costs ~6s a frame against Eevee's ~0.8s, and earns it twice
over: it actually transports light, and it renders pixel-identical
across runs where Eevee drifted by 1 LSB, which is what lets the
checked-in fixtures regenerate reproducibly.

What the scene still does **not** model, so no result here is evidence
about it: geometric depth (the bezel is painted on a flat plane, so it
never occludes a marker at an oblique angle), lens distortion, rolling
shutter, and panel content detailed enough to produce false-positive
quad candidates for the detector.

Blender buys one thing a warped 2D canvas can't: each frame's
ground-truth aim point is computed from the rendering camera's own pose
— where its optical axis meets the panel plane — with no homography
involved. So the test checks `solve.py` against an independent
reference rather than against its own arithmetic. `scene.blend` is
checked in alongside the frames so the scene can be opened and
inspected rather than only re-derived from a script.

A second fixture, `tests/fixtures/close_range/`, renders the same scene
from close in, where the bezel markers fall outside the frustum. Its
poses were chosen to yield 0, 1, 2 and 3 visible markers, so Deck B
covers "cannot solve at all" through "solvable but extrapolating"
through "partial but still well-conditioned".

Regenerating either needs Blender (`blender-5.2`; override with
`$BORESIGHT_BLENDER`). Running the tests does not — Blender is not a
project dependency:

    uv run python -m tests.generate_synthetic_video_fixture
    uv run python -m tests.generate_close_range_fixture

`detect.py` currently wraps `cv2.aruco.ArucoDetector` only — dictionary
match and corner extraction, no cornerSubPix refinement or
undistortPoints yet (those are separate Pipeline steps, still future
work). Per-frame behaviour over a synthetic frame sequence is covered
below; what's still missing is a real video source, 1-euro filtering,
and any wiring into `server.py`.

## Frame to cursor

`pipeline.py` is the composition: one frame in, one cursor move out. It
converts to greyscale, runs `detect.py`, looks each detected ID up in
the marker map, pairs its corners into correspondences, calls
`solve.py`, divides the millimetre aim point by the configured screen
size, and hands the normalized result to an `inject.py` backend. It
holds no state between frames.

Replay a recorded sequence through it — this is the whole path, and it
moves the real cursor:

    uv run python -m boresight.pipeline tests/fixtures/synthetic_video

Add `--dry-run` to print the aim track instead:

    frame    1  8 markers  aim (   300.7,    201.0) mm  cursor (0.2465, 0.2930)
    ...
    frame    3  1 markers  aim (    86.2,    342.1) mm  cursor (0.0707, 0.4987) EXTRAPOLATED
    frame    1  0 markers  no emission: no_markers

`solve.py` deliberately decides nothing about a low-confidence aim
point, leaving it to whoever consumes one. `pipeline.py` is that
consumer, so it has to answer four questions, and being stateless
constrains every answer:

| Case | Behaviour |
| --- | --- |
| Nothing to solve from (no markers, or fewer than four correspondences) | Emit nothing, return an outcome. Not an exception — dropout is the steady state, not an error |
| Solve flagged as poorly conditioned | **Emit it**, and report the flag |
| Aim point off the panel | Clamp into `[0, 1]` at the emission boundary, and report that it was clamped |
| Detected ID absent from the map | Ignore it, count it, solve from the rest |

Emitting flagged solves is the one worth arguing about. Flagged does not
mean wrong — the close-range fixture's one- and two-marker poses are
flagged and still land within a few mm — and suppressing them would
blank the cursor in exactly the close-range case the midpoint marker
ring exists to serve. But the same flag also covers the single-marker
extrapolation measured 2m off, which clamps to a screen corner and looks
like a plausible cursor position. Without temporal state there is no
principled way to tell those apart — which was the argument for a
1-euro filter, now added a layer below this one (see "Aim smoothing").

So what's still absent from `pipeline.py` itself, and deliberately: **no
filtering, and no hold-last-good-and-decay on dropout.** An unsolvable
frame simply leaves the cursor where it was rather than inventing a
position. Smoothing lives outside this module on purpose, so it stays
true; see "Aim smoothing" for where it actually lives.

Tests are in two layers. `tests/test_pipeline.py` stubs the detector to
drive each policy branch directly; `tests/test_pipeline_e2e.py` replays
both checked-in fixtures through the real detector into a fake backend
and asserts the emitted track against the manifests' ground truth.

One measured caveat about the full-visibility deck, recorded because it
is the kind of thing that lets a bug ship: with all eight markers in
frame, accuracy is nearly insensitive to how corners are paired.
Reversing the map's corner order to counter-clockwise — reflecting every
marker about its own diagonal — costs just 1.77mm, well inside the 4mm
tolerance, because RANSAC averages a per-marker permutation away across
32 correspondences. The sparse close-range assertions catch it, since
there the permutation is the entire fit. Corner order is pinned exactly
in a unit test; the full-visibility numbers should not be trusted for it.

## Aim smoothing

`one_euro.py` implements a one-euro filter (Casiez et al.) over the
normalized 2D aim position, and `inject.py`'s `SmoothingCursorBackend`
wraps it around a `CursorBackend`: `move_absolute` runs its input
through the filter before forwarding it, `click` passes straight
through. It lives at that seam rather than inside `pipeline.py` on
purpose — `AimPipeline` stays exactly as stateless as the section above
describes, and one `SmoothingCursorBackend`, built once by
`MarkerSourceController`, keeps the same filter state across a
marker-source switch instead of resetting it every time the pipeline is
rebuilt.

The tradeoff is the point: a steady aim is smoothed heavily (frame-to-
frame detection noise stops reading as visible dribble), while a fast,
sustained swing to a new target is smoothed much less, so it does not
feel laggy. Both follow from the same speed-adaptive cutoff — see the
module docstring for the formula.

`POST /cursor/move` is unaffected: the route keeps the raw, unwrapped
backend from `app.state.cursor_backend`, so an explicit requested
coordinate always lands exactly, never smoothed toward wherever
aim-derived movement last left the filter.

### Holding through a brief dropout

`aim_hold.py`'s `HoldingPipeline` wraps an `AimPipeline`: on a frame
that does not solve, if a solved frame landed within the last 0.75s, it
re-sends that same position to the (smoothing-wrapped) cursor backend.
This exists because of a real platform behaviour, not a solving
concern — a Wayland compositor hides a pointer that produces no events
for a while, and an ordinary short dropout (a marker briefly occluded,
motion blur) would otherwise read as the OS cursor blinking out and
back. Re-sending an unchanged position through the one-euro filter
converges to that same position regardless of elapsed time, so holding
cannot itself introduce a jump — only fresh device traffic. Once the
window lapses with no new solve, holding stops and the cursor is
allowed to go idle. `MarkerSourceController` builds a fresh
`HoldingPipeline` per marker source, so a switch does not carry a held
position from the old source into the new one. The wire report and
debug overlay are unaffected either way — a held frame is still
reported exactly as the unsolved frame it is.

## The phone client

The phone loads a page in its browser, which captures from the rear
camera and streams frames to the PC. Nothing is installed on the phone.
The page also links to the printable marker sheet (`GET /markers`), with
the token carried through, so the tags can be reached from whichever
device is in front of a printer without hunting for the URL.

### Read this first: the camera needs a secure context

**A phone loading `http://192.168.1.20:7331` will find no camera API at
all.** Not a denied permission — `navigator.mediaDevices` is simply
absent. Browsers expose capture only in a secure context, and a LAN IP
over plain HTTP is not one. `localhost` is the sole exemption.

This is the first thing that will stop you, and the symptom does not
suggest the cause, so the client detects it and says so on screen.
There are two ways through:

**1. USB, no certificate** — the better path, and the one to measure
with. Plug the phone in and forward the port:

    adb reverse tcp:7331 tcp:7331
    uv run python -m boresight.server

Then open `http://localhost:7331` on the phone. `localhost` is a secure
context, so there is no certificate, no interstitial, and no Wi-Fi hop
in the latency you are trying to measure.

**2. TLS over Wi-Fi** — how it is actually meant to be played:

    uv run python -m boresight.server --host 0.0.0.0 --token-auto --tls

which prints the exact URL to open, token included:

    Open this on the phone:  https://192.168.1.20:7331/?token=xK3f...

The certificate is self-signed, so the phone shows a warning the first
time. It is generated once into `.boresight/` and reused, so accepting
it is a one-time cost rather than a per-restart one.

### Opening the port in the firewall

Only for the Wi-Fi path. The USB path above needs no firewall change at
all — `adb reverse` carries the connection over the USB cable and the
server never leaves loopback, which is one more reason to start there.

Most desktop Linux ships with a firewall that drops inbound connections
by default, so the server binds `0.0.0.0` successfully, prints its URL,
and the phone still cannot reach it. The symptom is unhelpful: the
phone's browser just spins and times out, and the server logs nothing,
because the packets never arrive.

Diagnose it before changing anything. On the PC:

    ss -ltnp | grep 7331

If that shows the server listening but the phone times out anyway, it is
the firewall (or the two devices are on different networks — guest Wi-Fi
and AP isolation both do this, and no firewall rule will fix that).

**firewalld** (openSUSE, Fedora, RHEL). The examples below use the
`home` zone, which is the right place for a rule like this: a trusted
home network, not whatever the machine might join later. Confirm your
Wi-Fi interface is in it before adding anything — a rule added to a zone
the interface is not in succeeds, reports success, and changes nothing:

    firewall-cmd --get-active-zones

Try it without persisting first, so a reload or reboot undoes it:

    sudo firewall-cmd --zone=home --add-port=7331/tcp

Once the phone connects, keep it:

    sudo firewall-cmd --zone=home --add-port=7331/tcp --permanent
    sudo firewall-cmd --reload

**ufw** (Ubuntu, Debian). Scope it to your subnet rather than opening the
port to everything:

    sudo ufw allow from 192.168.1.0/24 to any port 7331 proto tcp

**Windows** (the future `SendInput` path), in an elevated PowerShell:

    New-NetFirewallRule -DisplayName "Boresight" -Direction Inbound `
      -LocalPort 7331 -Protocol TCP -Action Allow -Profile Private

Use whatever port you passed to `--port`; 7331 is only the default.

**Scope the rule to your LAN.** What you are exposing is an endpoint
that moves your mouse and clicks it. The token is what stands in front
of it, and a firewall rule limited to the local subnet is the second
layer — worth having, because the token also travels in a URL and ends
up in browser history. firewalld can be told the same thing precisely:

    sudo firewall-cmd --permanent --zone=home --add-rich-rule='rule family=ipv4 source address=192.168.1.0/24 port port=7331 protocol=tcp accept'

(One line — the rule is a single argument, and a backslash inside the
quotes would land in the rule text rather than continuing the command.)

To close it again afterwards:

    sudo firewall-cmd --zone=home --remove-port=7331/tcp --permanent
    sudo firewall-cmd --reload

### The server will not open itself up without a token

Binding a non-loopback address without `--token` or `--token-auto` is a
startup failure, not a warning:

    refusing to bind 0.0.0.0: a token is required to serve a
    network-reachable address.

The thing being prevented is severe and has no local symptom: an
endpoint on your network that moves your mouse, reachable by anything
that joins the Wi-Fi. Once set, the token is required on *every*
endpoint — the client page, the marker sheets, `/cursor/move`, and the
frame socket. It travels as a `?token=` query parameter, because a
browser cannot set headers on a WebSocket handshake; HTTP callers may
use `Authorization: Bearer` instead.

Loopback with no token keeps working exactly as before. Nothing is
exposed, so nothing is demanded.

### Wire protocol

One binary WebSocket message per frame, to `/ws/frames`:

    [8 bytes: float64 LE, client capture time in ms][JPEG bytes...]

Text messages on the same socket carry JSON — telemetry from the server,
control from the client. The trigger will land there without needing a
second connection or any change to frame handling.

JPEG rather than a video codec: `MediaRecorder` produces chunks whose
boundaries do not align to frames, so the server would have to demux a
running stream to recover the per-frame images the pipeline needs. JPEG
costs bandwidth and buys frame clarity — and it is what the rendered
fixtures already are, so a fixture file is a wire payload, and the
end-to-end test streams the checked-in frames down a real socket and
asserts the cursor track is *identical* to replaying them from disk.

The timestamp is echoed back untouched. The server cannot compute
round-trip time itself — the two clocks share no epoch — so the phone
subtracts against its own monotonic clock and reports the result back.

### Frames that arrive too fast are dropped, newest first

If the pipeline falls behind, the server keeps only the most recent
unprocessed frame and discards whatever was waiting. It does not queue.

A queue turns a throughput shortfall into unbounded, monotonically
growing lag: ten seconds into a session the cursor follows where you
aimed a second ago, and it never recovers. Dropping costs nothing,
because the frame being discarded is strictly worse information than the
one replacing it. The client applies the same rule one hop earlier,
skipping a capture when the socket's `bufferedAmount` has not drained.

Every drop is counted and reported rather than hidden.

### Telemetry

The phone displays, per frame: round-trip time, markers detected,
normalized aim point (flagged when extrapolated), frames sent /
processed / dropped / failed, and server-side decode and solve times.

**No latency figure has been measured yet.** This change builds the
instrument; reading it needs a real phone on a real network. Locally,
decode and solve are each around 5 ms on the 1280x720 fixtures, which
bounds the PC-side cost and says nothing at all about the hop. README's
condition for moving to WebRTC is that WebSocket latency proves too
high — that is now a measurement rather than an assumption.

Every capture default (resolution, rate, JPEG quality, exposure value)
is a guess made without hardware. They are all in `CONFIG` at the top of
`capture.js`, and the telemetry exists to replace them.

Still absent, deliberately: **no filtering and no dropout decay.** An
unsolvable frame leaves the cursor where it was rather than inventing a
position; holding the last good pose and decaying it needs state the
per-frame path does not have, and is the next thing to build.

## On-screen markers

Instead of printing the tags and sticking them to the bezel, draw them
on the display. This is the Sinden approach with ArUco instead of a
white frame, and it removes three costs at once:

- **Nothing to print** at a verified physical size, and nothing to cut
  or tape to a television.
- **Nothing to measure.** The positions are known exactly in pixels, so
  the marker-map calibration milestone does not apply.
- **No exposure problem.** The tags are emissive, so the dominant
  failure mode in "Known failure modes" — paper beside a bright panel,
  auto-exposure chasing the screen, tags underexposing to mud — is not a
  failure mode they have.

It also relieves the minimum working distance. Printed tags sit
*outside* the panel, so a close camera loses all of them: measured at
zero detected markers below 1400mm. On-screen tags sit inside the
panel, so a close camera keeps seeing them.

    uv sync --extra overlay
    uv run python -m boresight.server

Then tap **On-screen** in the Markers row on the phone. The server
starts the overlay, learns the display size from it, and switches the
solver to match — no second terminal, no restart, and no resolution to
get right by hand. Tap **Printed** to stop it.

The switch reaches a phone that is already streaming, on the next
frame, so you can flip between the two while aiming and watch the
difference.

Starting the overlay this way needs the server running **inside the
desktop session**, not headless — it has to reach a display. A server
that cannot will say so on the phone rather than failing quietly.

You can also run the overlay yourself and select the layout at startup,
which is what a scripted or headless deployment wants:

    uv run python -m boresight.overlay          # one terminal
    uv run python -m boresight.server --markers screen:1920x1080

`--markers` takes `file` (the shipped printed layout, the default),
`file:<path>` for one of your own, or `screen:<W>x<H>`. Printed and
on-screen markers are alternatives, not a migration — nothing about the
printed path changed.

### What it costs

About **6.5% of the picture**, near-constant across resolutions,
occluded by eight tags and their quiet-zone patches. Only those patches
are painted; the rest of the display shows through untouched.

The tag size is derived from README's own sizing table rather than
picked — roughly 3px per bit cell over a 6x6 grid, allowing for the
display filling part of the camera frame — and works out at 4.5% of
screen width. Override with `--tag-px` if your playing distance is
unusual.

| Display | Tag | Inset | Occludes |
| --- | --- | --- | --- |
| 1280x720 | 58 px | 14 px | 6.4% |
| 1920x1080 | 86 px | 22 px | 6.5% |
| 2560x1440 | 115 px | 29 px | 6.5% |
| 3840x2160 | 173 px | 43 px | 6.5% |

### A monitor whose panel isn't detected

The overlay avoids desktop panels and docks automatically, by asking
the windowing toolkit for the display's available area. On a
multi-monitor Linux/X11 or XWayland setup this can under-report: the
`_NET_WORKAREA` property it reads is one rectangle for the whole
virtual desktop rather than one per monitor, so a monitor whose panel
happens to fall outside that single rectangle's reserved band is
reported as having no reservation at all — confirmed on a real
multi-monitor machine, where a taskbar visibly covered a tag near a
monitor's edge despite the overlay's own log reporting nothing
reserved there.

`--extra-margin-px` shrinks the auto-detected area by that amount on
every side, on top of whatever was already found — zero by default, no
effect unless set:

    uv run python -m boresight.overlay --extra-margin-px 50

Threaded through the server too, for the normal (phone-driven) way of
starting on-screen markers:

    uv run python -m boresight.server --overlay-extra-margin-px 50

The CLI flag only sets a starting value, though — judging whether a tag
now clears a taskbar means looking at the display, which is where the
phone is, not the machine running the server. The phone client's
Markers row has a `−`/`+` stepper for it next to the source buttons:
adjusting it takes effect immediately, restarting the overlay with the
new margin if on-screen markers are currently active (`POST
/markers/overlay-margin`), with no need to touch the server directly.

### The overlay is transparent to input

Every mouse and keyboard event passes straight through to whatever is
underneath. That is not a convenience feature — it is the only reason
this can work at all. Boresight injects its clicks *at the aim point*,
which is on the display the overlay covers, so an overlay that accepted
input would swallow every shot the gun fired. It would be shooting its
own overlay.

### Platform support, and where it stops

| Platform | Status |
| --- | --- |
| X11 | Supported |
| Windows | Supported in code, **never yet run by anyone** |
| Wayland — KDE, sway, Hyprland | Supported (layer-shell) |
| Wayland — GNOME | **Not possible.** Mutter does not implement `wlr-layer-shell`, so no client can place a surface above other windows |
| macOS | No backend |

Where it cannot work the overlay refuses to start and says why, rather
than showing a window that renders but sits in the normal stacking
order and eats input. That failure would look like a Boresight bug
instead of a compositor limitation.

**No overlay can draw above a fullscreen-*exclusive* application**, on
any platform. Run emulators borderless-windowed. This is the same
constraint noted in "Cursor injection" for synthetic events reaching
fullscreen-exclusive titles.

The obvious objection is that FPS counters manage it — RTSS, the Steam
and Discord overlays, MangoHud. They do, by not being overlays: they run
*inside* the game process and hook the presentation call
(`IDXGISwapChain::Present`, `vkQueuePresentKHR`), drawing into the back
buffer before it reaches the display. That approach would also sidestep
the Wayland limitation above. It is not built here because a
software-rendered emulator presents no swapchain to hook, it requires
launching the game *through* the layer, and on Windows it means DLL
injection. Worth revisiting if borderless-windowed turns out not to be
enough.

## Repo layout

Target layout for the full pipeline — some of this doesn't exist yet.
Everything not marked `# future` is built; see "Running the server",
"Homography solving (standalone)", "Frame to cursor" and "The phone
client" above.

Data files live **inside** `src/boresight/`, not beside it. The wheel
packages that directory and nothing else, so a layout or client file
one level up works from a checkout and 404s from an installed copy —
a defect invisible to a test suite that always runs from a checkout.

    boresight/
      pyproject.toml
      src/boresight/
        config/
          markers.toml        # id -> (x, y) in screen mm; reference layout
          camera.toml         # future: intrinsics + distortion
        web/
          index.html          # phone client: capture, status, telemetry
          capture.js          # getUserMedia, JPEG encode, WebSocket send
        server.py             # HTTP + frame socket, serves web/ to the phone
        stream.py             # frame codec, drop slot, per-session counters
        netaccess.py          # bind address, shared token, TLS certificate
        detect.py             # ArUco detection (+ future subpixel refinement)
        marker_map.py         # markers.toml -> id to screen-plane corners
        markers.py            # printable marker SVG, served over HTTP
        solve.py              # homography, RANSAC, aim point
        pipeline.py           # frame -> detect -> solve -> normalize -> inject
        layout_source.py      # printed layout or on-screen, by config
        overlay/
          layout.py           # where on-screen tags go (shared by both sides)
          render.py           # painting them
          backend.py          # can this platform host an overlay?
          qt_backend.py       # the always-on-top, input-transparent window
        inject.py             # uinput backend (+ future SendInput); SmoothingCursorBackend
        one_euro.py           # the 1-euro filter SmoothingCursorBackend wraps
        serial_link.py        # future: optional ESP32 HID path
        debug_overlay.py      # future: quads, IDs, reprojection error
      tools/
        calibrate.py          # future: chessboard intrinsics
        map_markers.py        # future: build markers.toml for a real TV
      firmware/
        boresight-hid/        # future: ESP32-S3, TinyUSB hardware path
      tests/
        fixtures/             # rendered frame sequences (Git LFS)

### markers.toml

    screen_width_mm = 1220
    screen_height_mm = 686

    [[marker]]
    id = 0
    x = -120
    y = -120
    size_mm = 80

    [[marker]]
    id = 4
    x = 570
    y = -120
    size_mm = 80

Origin is the top-left of the active display area, x rightwards and y
downwards, in millimetres. Each marker's `x`/`y` is its own top-left
corner. Negative coordinates — and coordinates past the screen size —
mean the tag sits on the bezel outside the panel, which is where all
eight of them are.

`size_mm` is per marker rather than per layout, so the inner ring for
close play can use smaller tags without a format change.

`src/boresight/config/markers.toml` ships the **reference layout**: the
one the checked-in Blender fixtures render and every accuracy figure
below was measured against. It is not a layout for your TV — a real
installation needs its own measurements, which is what the (unbuilt)
marker map calibration tool is for. A test asserts the shipped file and
the fixture manifests stay in agreement, so the config and the rendered
scene cannot drift apart silently.

It sits inside the package and is resolved relative to the module, not
the working directory, so it ships in the wheel and loads the same from
anywhere.

`marker_map.py` loads and validates the file and answers the one
question detection cannot: given a detected marker ID, where are that
marker's four corners on the screen plane? It returns them clockwise
from top-left, matching the order `cv2.aruco` reports detected corners
in, so the two sequences pair positionally.

## Milestones

- [ ] Generate and print markers at verified physical size — `GET
      /markers` and `GET /markers/{id}.svg` (`markers.py`) serve
      print-ready vector tags at exact mm dimensions from the browser;
      verifying a physical print against a ruler is still a manual step
- [ ] Camera intrinsic calibration (phone camera)
- [x] Web server: phone connects over Wi-Fi, streams video, PC decodes
      frames — the client page, the frame socket, the newest-wins drop
      policy, token auth and TLS all exist and are tested by replaying
      the checked-in fixtures through a real socket (see "The phone
      client"). Never yet run against an actual phone, so every capture
      default is an untested guess and no latency has been measured
- [ ] Detection on a tripod against streamed frames, print raw marker IDs and corners
- [ ] Marker map calibration tool — the file format and its loader
      (`markers.toml`, `marker_map.py`) exist and ship a reference
      layout; measuring a real TV into one is still manual. Only needed
      for printed markers: on-screen markers know their own positions
      exactly (see "On-screen markers")
- [x] Homography solve, print screen coordinates: `solve.py` implements
      `findHomography` + RANSAC + inverse-mapped aim point, tested
      against synthetic correspondences, a synthetic rendered image, and
      a Blender-rendered frame sequence covering per-frame accuracy and
      frame-to-frame coherence (see "Homography solving (standalone)") —
      built ahead of the pipeline above, like cursor injection; not yet
      wired to a real video/detection source
- [x] Frame-to-cursor pipeline: `pipeline.py` composes detection, the
      marker map, the solver and cursor injection into one stateless
      per-frame call, replayable over the checked-in fixtures with
      `python -m boresight.pipeline` (see "Frame to cursor"), and now
      also fed live by the phone over a WebSocket — smoothed by a layer
      below it, not by the pipeline itself (see "Aim smoothing")
- [x] On-screen markers: `python -m boresight.overlay` draws the tags
      over the live display, always on top and transparent to mouse and
      keyboard, with the solver and the renderer sharing one layout
      function so they cannot disagree (see "On-screen markers") — X11
      verified offscreen, never yet run against a camera or on Windows
- [ ] Debug overlay with per-frame reprojection error
- [x] 1-euro filter tuning: a `CursorBackend` decorator (`inject.py`'s
      `SmoothingCursorBackend`, over `one_euro.py`) smooths aim-derived
      cursor movement before it reaches the OS, with defaults tuned by
      feel rather than measurement; does not affect `POST /cursor/move`
      (see "Aim smoothing")
- [x] Cursor injection scaffolding: FastAPI endpoint moves the OS cursor
      directly (uinput, Linux) — built ahead of the pipeline above as a
      standalone proof; not yet wired to real aim data or Mesen
- [ ] SendInput injection (Windows), test in Mesen
- [ ] On-screen trigger button wired to click injection — the frame
      socket already reserves text messages for it, so it needs no
      second connection
- [ ] Integrate phone mount into shell
- [ ] Wi-Fi latency/jitter measurement and tuning — the instrument
      exists (round-trip time and drop counts are on the phone's
      screen); nobody has read it against real hardware yet
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

**Multi-gun.** Marker detection is per-camera and stateless, so two guns
need no coordination beyond distinct WebSocket connections and device IDs.

## Notes

"NES", "Zapper", and "Duck Hunt" are Nintendo trademarks. This project is
not affiliated with or endorsed by Nintendo. Compatibility with emulators
is described factually; no trademarked terms appear in the project name,
branding, or any distributed artifact.

## License

MIT
