## Context

`detect_markers()` runs one full-resolution `ArucoDetector` pass per
frame, on a per-thread detector (see the `improve-marker-detection`
change). The server decodes each JPEG to colour and `AimPipeline`
converts it to grey. `AimPipeline` is shared by every session and
promises to hold nothing between frames; per-session state
(smoothing, hold) lives in `SessionPipeline`/`HoldingPipeline`, and
per-session inputs reach the pipeline as per-call arguments (`backend`,
`debug`). A session has at most one frame in flight.

Lens calibration is landing concurrently and will undistort corners
between detection and solve, so the detection output contract --
corners in full-resolution original-image pixels -- must not change.

## Goals / Non-Goals

**Goals:** cut per-frame CPU on a slow machine without any measurable
loss of corner accuracy or detections; keep every miss recoverable in
the same frame; bound how long a newly visible marker can go unseen;
keep state per session; allow turning it off.

**Non-Goals:** changing `detect_markers()` or its parameters; GPU or
multi-process detection; tuning the adaptive-threshold windows (that
trades robustness, which this change must not).

## Measurements

All numbers from `tests/measure_detection_speed.py` (and a scratch
prototype for the rejected strategies), AMD Ryzen AI Max+ 395, OpenCV
5.0.0, **one OpenCV thread** (the slow-PC case) unless noted; medians
of 15 passes over each fixture.

Detection, full pass vs. tracked (coarse-to-fine as adopted):

| Fixture | Marker side | Full | Tracked | Coarse frames | Corner dev. vs full | Aim max/mean, full → tracked |
|---|---|---|---|---|---|---|
| synthetic_photo 1920x1080 (still x20) | ~96px | 27.2ms | 4.8ms | 18/20 | 0.026px | GT corner err mean/max 0.288/0.417 → 0.289/0.407px |
| synthetic_video 1280x720 | 38-40px | 3.25ms | 2.09ms | 18/20 | 0.041px | 1.48/1.39 → 1.47/1.39mm, delta max 0.09 → 0.09mm |
| esp32cam_video 1024x768 | 23-25px | 5.11ms | 5.18ms | 0/20 | 0 (identical) | identical |
| close_range 1280x720 (7 unrelated poses) | 80-90px | 2.53ms | 2.70ms | 0/7, 1 miss | 0 (identical) | identical |

With OpenCV's default threads (32 here): photo 12.2 → 2.3ms, phone
video 1.73 → 1.16ms, ESP32 2.59 → 2.75ms, close range 1.06 → 1.26ms.
No fixture lost or gained a detection. The ESP32 and close-range rows
are the cost side: tracking overhead is ~0.05-0.1ms of Python per
frame, plus one wasted coarse pass per miss (close_range teleports
between poses, the worst case).

JPEG decode (1 thread): colour + `cvtColor` vs. `IMREAD_GRAYSCALE`:
phone 1.87 → 1.26ms, ESP32 1.44 → 0.92ms, close range 1.73 → 1.10ms.
Detections from the greyscale decode were identical on every fixture
(0 missed, 0 extra, 0.000px corner deviation), though individual
pixels differ by up to 11 grey levels.

Per-frame total on the phone fixture, one thread: ~5.1ms (1.87 decode
+ 3.25 detect) → ~3.4ms (1.26 + 2.09), about 1.5x the frame rate a
CPU-bound core can sustain; at 1080p detection alone goes from 27ms
to under 5ms.

Coarse pass vs. marker size (scratch sweep: fixtures upscaled, coarse
pass alone, no fallback): phone frames found every marker at every
size from 38px to 94px; ESP32 frames lost 56/137 detections at 23px,
52 at 29px, 25 at 35px and still 11-13 at 46-54px, with individual
corners up to 2-9px off at the larger sizes -- but solved aim error
over the sequence stayed within ~0.4mm of the full pass's from 35px
up (e.g. 1.5x: 1.88 vs 1.74mm max), while at native 23px it was
16.2mm max vs 2.4mm.

## Decisions

**Coarse-to-fine over ROI tracking.** A prototype searching only
padded windows around each last-seen marker (merged when overlapping,
full-frame fallback when a tracked marker is lost, full pass every 10
frames) measured: phone video 3.19 → 2.58ms (-19%), ESP32 5.05 →
7.08ms (+40%: its detections flicker, so 13/20 frames paid ROI + full),
close range no gain. The fixtures move ~55px/frame, so windows must be
wide and the saving is small; the coarse pass saved twice as much with
no dependence on motion. ROI is not adopted; stacking it on the coarse
pass was not worth a second fallback path for the remaining ~2ms.

**OpenCV's ArUco3 pyramid (`useAruco3Detection`) rejected.** Same
parameters otherwise: it missed 9/160 phone detections at
`minMarkerLengthRatioOriginalImg=0`, all 160 at 0.02, and every ESP32
detection at any ratio, with corners up to 9px from the full pass on
close range.

**Two refinements in the coarse pass.** The detector refines on the
half-size image as usual; the corners are mapped back
(`(c + 0.5) / scale - 0.5`, the area-averaging pixel-centre offset) and
refined again with `cornerSubPix` on the full-resolution image, with
the same window rule OpenCV uses (one module, capped at 5px). With the
bare contour vertex as the starting point, noisy ESP32 corners started
up to 6px out -- beyond a 5px window -- and stayed there; the small-
image refinement brings the start within reach.

**Half scale, `INTER_AREA`.** `resize` at exactly 0.5 with area
averaging costs ~0.03ms at 720p; at 0.75 the resize made the coarse
pass slower than the full one (3.4 vs 3.2ms). `pyrDown` was 4x slower
than `resize` for the same job.

**Gate on the last frame's smallest marker, fall back on doubt.** The
coarse pass runs only while every marker the last frame found was
≥36px (18px at half size, 3px per module). Its result stands only if it
re-found every tracked id and found nothing below 36px; otherwise the
full pass runs on the same frame. 36px sits just under the phone
fixture's smallest marker and well above the ESP32's; the sweep shows
ESP32-quality images losing detections even at 46-54px, which the
fallback absorbs (a lost tracked marker forces the full pass). After a
coarse miss the next 10 frames go straight to the full pass, so a
camera the coarse pass keeps failing on wastes at most one coarse pass
per 10 frames.

**A full pass at least every 10 frames.** The coarse pass can find new
markers only if they are big enough; the periodic full pass bounds
discovery of any detectable marker to 10 frames (~0.33s at 30fps) and
re-baselines the tracked set. It also caps the steady-state saving at
90% of frames.

**Per-call detector, pipeline stays stateless.** `process_frame` takes
`detector=` like it takes `backend=`; `AimPipeline.session_detector()`
returns a new `MarkerTracker` when the pipeline uses the real detector
with tracking on, and the pipeline's own detector otherwise -- so a
stubbed test pipeline is never bypassed and `--full-frame-detection`
yields exactly today's path. `SessionPipeline` asks for one whenever it
(re)builds its `HoldingPipeline`, so a marker-source switch starts a
fresh tracker along with a fresh hold. `replay()` uses one per sequence
and reads frames greyscale, so replay and streaming stay identical.

**Greyscale decode unconditionally.** It is not gated by the option:
the benchmark shows identical detections, and the pipeline converts to
grey immediately anyway. `_as_grayscale` stays for colour callers.

## Risks / Trade-offs

- [Coarse corners differ from full-pass corners by up to ~0.04px on
  the phone fixture] → bounded in the spec at 0.1px and asserted by
  test; aim error and jitter are unchanged to 0.01mm.
- [Real cameras noisier than the fixtures could make the coarse pass
  miss often] → every miss of a tracked marker falls back in the same
  frame, and backoff limits the wasted work to one coarse pass per 10
  frames (~+5-10% over full-frame in that case).
- [A marker new to the view and too small for the coarse pass is seen
  up to 10 frames late] → only while other, larger markers are
  tracked, so the frame still solves; bounded by the periodic pass.
- [A marker the coarse pass finds that the full pass would not] →
  accepted: it is a real dictionary decode, refined at full resolution,
  and must be ≥36px. None occurred on the fixtures.

## Migration Plan

On by default. `--full-frame-detection` restores full-frame detection
on every frame; nothing persists, so rollback is a restart.
