## Why

`solve.py` fits its homography to detected marker corners and nothing
else, so every bit of corner noise becomes aim noise. `detect.py` hands
it the corners `cv2.aruco` produces with its defaults, which means no
refinement at all: corners sit on the contour's polygon vertices, off
the true edge by up to ~2px on the checked-in photo. README's Pipeline
already calls cornerSubPix refinement a step "easy to skip and
shouldn't be". Meanwhile the detector is rebuilt from scratch on every
frame, even though the server now runs frames from several sessions
concurrently on executor threads, where one shared instance would need a
thread-safety guarantee OpenCV does not document.

## What Changes

- Marker corners are refined to sub-pixel accuracy before they leave
  `detect.py` (`CORNER_REFINE_SUBPIX`, search window scaled to the
  marker's module size), with parameters measured against every fixture
  that has ground truth, including the low-resolution ESP32-CAM one.
- The detector is built once per thread and reused, instead of once per
  frame; concurrent frames on different threads never share one.
- A measurement script (`tests/measure_detection.py`) prints corner
  error, aim error, jitter and time per frame for each fixture, before vs
  after, so future detector changes can be judged on the same numbers.
- Regression tolerances that the improvement makes loose are tightened
  (full-visibility video, realistic photo, partial-visibility deck), and
  a direct corner-accuracy test is added so losing refinement fails as
  itself rather than only as aim drift.

## Capabilities

### New Capabilities
- `marker-detection`: finding markers in a frame and localising their
  corners: sub-pixel corner accuracy, and detection that is safe to run
  from several threads at once with consistent results.

### Modified Capabilities
(none. The solver's and pipeline's requirements already say "within a
documented tolerance"; this change tightens the documented numbers, not
the requirements.)

## Impact

- Changed code: `src/boresight/detect.py`. Its public entry point
  `detect_markers(image)` keeps its signature, so `pipeline.py` and all
  callers are unchanged.
- Tests: new `tests/test_detect.py` and `tests/measure_detection.py`;
  tighter tolerances and refreshed observed-value comments in
  `test_solve_video_e2e.py`, `test_solve_e2e_realistic.py`,
  `test_solve_partial_markers.py`, `test_solve_close_range.py`.
- README: the paragraph that said `detect.py` has no refinement.
- No new dependencies, no wire-format or API change. Detection cost per
  frame is unchanged within measurement noise.
