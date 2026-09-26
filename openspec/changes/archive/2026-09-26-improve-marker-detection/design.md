## Context

`detect.py` built `cv2.aruco.ArucoDetector(dictionary,
DetectorParameters())` inside `detect_markers` on every call and used
OpenCV's defaults, where `cornerRefinementMethod` is
`CORNER_REFINE_NONE`. `AimPipeline` holds `detect_markers` as its
injectable `Detector` callable. One pipeline serves every streaming
session, and `server.py` runs each frame's decode+solve through
`loop.run_in_executor(None, ...)`, the default thread pool. So frames
from different sessions can be in detection at the same moment on
different threads.

Installed OpenCV is 5.0.0. In 4.7+ the SUBPIX window is not just
`cornerRefinementWinSize`: the effective half-size is
`min(cornerRefinementWinSize, relativeCornerRefinmentWinSize x module
size)`, where a module is one bit cell of the marker (a 4x4 marker with
its border is 6 modules across). The default relative factor is 0.3.

Fixtures with ground truth used for measurement:

| Fixture | Frames | Size | Markers | Ground truth |
| --- | --- | --- | --- | --- |
| synthetic_photo | 1 | 1920x1080 | 8, ~95px | homography, so corners **and** aim |
| synthetic_video | 20 | 1280x720 (phone) | 8 per frame | aim point per frame |
| esp32cam_video | 20 | 1024x768, noisy, heavy JPEG | 6-8, ~25px | aim point per frame |
| close_range | 7 | 1280x720 | 0-3 | aim point per frame |

## Goals / Non-Goals

**Goals:**
- Sub-pixel corners, with parameters chosen by measurement on every
  fixture above, the ESP32-CAM one included.
- A detector built once and reused, safe under the server's concurrent
  executor threads.
- A repeatable before/after measurement checked into the repo.

**Non-Goals:**
- `undistortPoints` / intrinsics. It stays a separate Pipeline step and
  needs the calibration milestone.
- Thresholding or contour tuning (`adaptiveThreshWinSize*`,
  `minMarkerPerimeterRate`, ...). Detection counts are already what the
  fixtures expect. Changing what gets *found* is a different change from
  changing where found corners *land*.
- The README accuracy table under "Marker visibility and accuracy". Its
  figures come from an earlier render of the fixture (4844 subset
  combinations; today's gives 5100), so they cannot be reproduced
  exactly by re-running either detector. Refreshing it is left to
  whoever next regenerates the fixtures. The numbers below are enough to
  do so.

## Decisions

### 1. `CORNER_REFINE_SUBPIX`, window one module wide

Settings: `cornerRefinementWinSize = 5`,
`relativeCornerRefinmentWinSize = 1.0`, `cornerRefinementMaxIterations
= 30`, `cornerRefinementMinAccuracy = 0.1`.

The deciding parameter is the relative factor, not `winSize`. With
OpenCV's default 0.3, the ESP32 frames' ~4px modules give a ~1px
half-window. That is too small to refine anything useful, and the
ESP32 fixture got **worse** (max aim 2.92 → 3.73mm), while `winSize` 2
through 7 made no difference at all. A window of one module reaches
from the corner to the inner edge of the black border, which covers the
corner's two edges and nothing else. Past that, it starts seeing the
data bits: at 1.5 modules with `winSize = 10` the phone video jumped to
9.5mm max error.

Sweep (aim error max/mean mm; Δ = worst frame-to-frame residual vs
ground truth; photo corner error mean/max px):

| Config | photo corners | photo aim | synthetic_video | esp32cam_video | close_range |
| --- | --- | --- | --- | --- | --- |
| none (before) | 0.75/1.88 | 1.31 | 1.90/1.39 Δ0.77 | 2.92/2.03 Δ1.50 | 0.59 |
| SUBPIX, OpenCV defaults (rel 0.3) | 0.32/0.42 | 0.79 | 1.62/1.42 Δ0.26 | **3.73**/2.24 Δ1.64 | 0.74 |
| SUBPIX rel 0.5, win 5 | 0.29/0.42 | 0.78 | 1.52/1.40 Δ0.12 | 2.67/2.19 Δ0.91 | 0.73 |
| SUBPIX rel 0.8, win 5 | 0.29/0.42 | 0.78 | 1.48/1.39 Δ0.09 | 2.42/2.18 Δ0.67 | 0.73 |
| **SUBPIX rel 1.0, win 5 (chosen)** | **0.29/0.42** | **0.78** | **1.48/1.39 Δ0.09** | **2.37/2.11 Δ0.41** | **0.73** |
| SUBPIX rel 1.0, win 10 | 0.17/0.26 | 0.76 | 1.51/1.34 Δ0.13 | 2.37/2.11 Δ0.41 | 0.72 |
| SUBPIX rel 1.5, win 10 | 0.17/0.26 | 0.76 | **9.54**/1.86 Δ9.45 | 4.45/2.41 Δ4.10 | 0.72 |
| CONTOUR | 0.71/0.94 | 0.87 | 1.80/1.30 Δ0.53 | 2.50/2.17 Δ1.24 | 0.72 |
| APRILTAG | 0.71/0.98 | 0.19 | 0.42/0.19 Δ0.49 | 1.60/0.51 Δ1.43 | 0.28 |

- **`winSize` 5, not 10.** 10 gives better photo corners (the only
  fixture with markers big enough for the cap to matter). But on the
  phone video it trades max error for mean (1.51 vs 1.48 max), and it
  sits one step from the 1.5-module blow-up for any marker whose module
  lands near 7-10px. 5 caps the window for markers larger than ~30px,
  where 5px is already a wide window.
- **Iterations / accuracy.** Swept 10/30/100 × 0.1/0.05/0.01 at the
  chosen window. No measured error moved by more than 0.01mm, so
  OpenCV's defaults stay.
- **APRILTAG rejected.** It has the best aim accuracy by far, but it
  costs 70-100ms per frame against ~2ms (415ms on the 1080p photo).
  It also *loses detections*: 137 → 107 markers on the ESP32 sweep, and
  9 → 8 on close_range, which breaks that fixture's recorded marker
  counts. A light gun cannot spend 35x its detection budget.
- **CONTOUR rejected.** It is marginally better than SUBPIX on ESP32 max
  error only under the default SUBPIX window. Against the chosen window
  it loses everywhere, and its phone-video jitter is 6x SUBPIX's.
- **Robustness to smaller markers.** The ESP32 and phone frames were
  re-run downscaled to 0.75x and 0.6x (markers ~19px and ~15px). At 0.6x
  on ESP32, max aim error is 79.8mm unrefined, 51.9mm at rel 0.5, and
  25.0mm at rel 0.8/1.0. At 0.75x it is 44.6 → 13.9mm (rel 1.0). The
  chosen setting helped at every scale tried and never made one worse.
- The photo's corner ground truth puts each marker's corner half a pixel
  before its first canvas pixel, the pixel-centre convention. With
  that, both detectors' errors are smaller than with the 0.0 offset
  (before 0.75 vs 1.06px mean), which is the check that the convention
  is right.

### 2. One detector per thread (`threading.local`), not one per process or per pipeline

OpenCV documents `detectMarkers` as `const`, but it does not document
`ArucoDetector` as safe to share across threads. The detector also holds
refinement and dictionary state behind a Python binding that we do not
control. A lock around one shared instance would serialise sessions
that run in parallel today. So `thread_detector()` builds a detector on
a thread's first call and keeps it in a `threading.local`. The executor
has a bounded number of worker threads, so this is a bounded number of
detectors.

- *Alternative: held by `AimPipeline`.* One pipeline serves all
  sessions, so a single instance there has the same sharing problem.
  Making the pipeline own a per-thread cache adds nothing that
  module-level `threading.local` does not already give, and it would
  change `AimPipeline`'s constructor and its injectable `Detector`
  seam. `detect_markers(image)` keeps its signature, and no caller
  changes.
- *Alternative: `functools.cache` per dictionary.* It gives one shared
  instance, which is what we are avoiding. The dictionary is a module
  constant anyway.

`test_concurrent_detection_matches_sequential` runs the 20 ESP32 frames
4x through a 4-worker pool and asserts byte-identical corners against a
sequential pass.

**Honest cost figure:** building the detector takes ~2.3µs (old
per-call construction) to ~2.8µs (new, with refinement parameters). So
caching saves about 0.1% of a ~2ms frame. The reason to cache is
structural: it gives a well-defined per-thread lifetime, and it puts
the parameters in one place instead of on the hot path. It is not a
speed-up. Refinement itself did not change detection time measurably
(table below).

### 3. Tolerances tightened to ~2x the new observed values

The policy is the one the tests already state (2-3x margin over
observed). Where possible, a bound also sits below the *unrefined*
value, so that losing refinement fails a test:

| Test | Before bound | New bound | Observed refined (unrefined) | Catches lost refinement? |
| --- | --- | --- | --- | --- |
| video e2e, synthetic_video aim | 4.0mm | 3.0mm | 1.48 (1.90) | no |
| video e2e, synthetic_video Δ | 4.0mm | 0.5mm | 0.09 (0.77) | **yes** |
| video e2e, esp32cam_video aim | 6.0mm | 5.0mm | 2.37 (2.92) | no |
| video e2e, esp32cam_video Δ | 4.0mm | 1.0mm | 0.41 (1.50) | **yes** |
| e2e realistic photo aim | 3.0mm | 1.5mm | 0.78 (1.31) | no |
| partial: inside-hull bound | 25mm | 6.0mm | 2.99 (11.89) | **yes** |
| partial: 4-corner subset | 4.0mm | 3.0mm | 1.49 (1.91) | no |
| new: photo corner max | n/a | 0.8px | 0.42 (1.88) | **yes** |
| clean synthetic image aim | 1.5mm | unchanged | 0.72 (0.77) | n/a |
| close_range enclosing frame | 5mm | unchanged | 0.73 (0.59) | n/a: one frame |

`SPARSE_ERROR_IS_STILL_BAD_MM` (100mm) is **not** changed, but its
margin shrank. Single-marker solves went from median 83.5mm / max
1017mm to median 13.5mm / max 132mm. The test asserts the worst case
is still > 100mm, and it now passes with 1.3x headroom instead of 10x.
That test exists to fail when sparse accuracy improves. Refinement is a
real improvement to it, but not the solvePnP fix the test is waiting
for, so the threshold stays and the comment records the new numbers.

## Measurements (before → after)

From `uv run python tests/measure_detection.py`. "Before" is OpenCV
defaults with the detector rebuilt per call (detect.py as of
47ec230). Times are detection only, on this dev machine, averaged over
10 passes:

| Fixture | Markers found | Corner err mean/max (px) | Aim err max/mean (mm) | Δ max (mm) | ms/frame |
| --- | --- | --- | --- | --- | --- |
| synthetic_photo | 8 → 8 | 0.75/1.88 → **0.29/0.42** | 1.31 → **0.78** | n/a | 10.4 → 9.7 |
| synthetic_video | 160 → 160 | n/a | 1.90/1.39 → **1.48/1.39** | 0.77 → **0.09** | 1.38 → 1.42 |
| esp32cam_video | 137 → 137 | n/a | 2.92/2.03 → **2.37/2.11** | 1.50 → **0.41** | 2.34 → 2.45 |
| close_range | 9 → 9 | n/a | 0.59 → 0.73 (1 frame) | n/a | 1.00 → 1.05 |

Partial-visibility sweep over every marker subset of every
synthetic_video frame (5100 solves):

| Subset | Before median / max (mm) | After median / max (mm) |
| --- | --- | --- |
| all markers | 1.4 / 1.8 | 1.4 / 1.5 |
| 4 corners | 1.4 / 1.9 | 1.4 / 1.5 |
| 2 markers, opposite | 4.1 / 15.3 | 2.3 / 6.1 |
| 2 markers, same edge | 17.5 / 487.7 | 7.9 / 24.2 |
| 1 marker | 83.5 / 1016.5 | 13.5 / 131.7 |
| any subset, inside hull | 1.5 / 11.9 | 1.4 / 3.0 |

The largest gains are exactly where corner error is amplified. The
worst case with every marker in view barely moves, because ~30
correspondences already average corner noise out. Extrapolated solves
from one or two markers improve 4-20x, and frame-to-frame jitter
drops 4-8x. That jitter is what README's "cursor vibrates at rest"
note is about.

The ESP32 fixture's *mean* aim error rose slightly (2.03 → 2.11mm)
while its max fell (2.92 → 2.37mm) and its jitter fell 3.7x. The one
close_range enclosing frame moved 0.59 → 0.73mm. Both are well inside
their tolerances. The residual on these fixtures is dominated by
something other than corner localisation (per-frame error is nearly
constant across detectors while the Δ drops to 0.1mm, which suggests
a consistent bias such as lens/render geometry that `undistortPoints`
would address), so a sub-0.2mm shift in the mean is noise, not a
regression. It was accepted after the parameter search above, which
removed the real ESP32 regression (3.73mm) that OpenCV's default window
caused.

## Risks / Trade-offs

- [The window is scaled to module size, so a marker imaged very small
  (<3px modules) gets a 1-2px window and little refinement] → This is
  the same or better than no refinement at every scale tried (0.6x
  downscale). Detection itself fails before refinement matters there.
- [`relativeCornerRefinmentWinSize` (sic, OpenCV's spelling) exists
  only from OpenCV 4.7] → `pyproject.toml` already requires
  `opencv-python-headless>=4.10`, and measurements were taken on 5.0.0.
- [Tighter tolerances fail on a legitimate fixture regeneration] → Each
  bound's comment states the observed value it came from, and
  `tests/measure_detection.py` reproduces those values in one command.
- [Per-thread detectors are never freed while a thread lives] → The
  default executor's thread count is bounded, and a detector holds only
  its parameters and the 50-entry dictionary.
- [Pre-existing, not caused by this change] `tests/test_stream_e2e.py`
  fails intermittently with a `CancelledError` from the server's
  websocket teardown racing an in-flight executor call, which is
  unrelated to detection. It failed 5/20 runs with the old detect.py and
  5/20 with the new one. It is left for a server-side change.
