## Why

Every frame pays for a full-resolution ArUco pass plus a colour JPEG
decode and a colour-to-grey conversion. On one OpenCV thread -- a
slower PC, or several sessions sharing cores -- that is ~5ms for a
1280x720 phone frame and ~27ms of detection alone for a 1920x1080 one,
which caps the frame rate a modest machine can keep up with. Most of
it is avoidable: the markers are usually where they were last frame,
at a size a half-resolution search finds just as well, and the colour
channels are thrown away immediately after decoding.

## What Changes

- A per-session `MarkerTracker` (`detect.py`) runs a coarse-to-fine
  pass -- detect on a half-size copy, refine corners at full resolution
  -- while the markers it last saw were large enough for that to be
  safe, and the existing full pass otherwise. Any doubt (a tracked
  marker missing, a marker found too small, nothing tracked) runs the
  full pass on the same frame; a full pass also runs at least every 10
  frames, so a marker entering the view is found within that bound.
  Output keeps the existing contract: corners in the original frame's
  full-resolution pixels.
- The pipeline takes the per-session detector per call, as it already
  takes the per-session backend, so `AimPipeline` stays stateless and
  shared. Each streaming session and each replay gets its own tracker;
  a marker-source switch starts a fresh one.
- The server and `replay` decode JPEG straight to greyscale instead of
  decoding colour and converting.
- `--full-frame-detection` on the server turns tracking off (full pass
  every frame, as before) for comparison or as a fallback.
- `tests/measure_detection_speed.py` benchmarks decode and detection
  time, markers found, corner deviation and aim error, full pass vs.
  tracked, per fixture. ROI (search-window) tracking and OpenCV's
  built-in ArUco3 pyramid were measured too and are not adopted.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `marker-detection`: adds per-session tracked detection -- the coarse
  pass's accuracy bound, same-frame fallback, bounded discovery of new
  markers, session isolation, and the switch to turn it off.
- `aim-pipeline`: the per-frame operation accepts a per-session
  detector per call without holding it, and replay uses one per
  sequence.
- `video-ingest`: each streaming session detects through its own
  tracker, and frames are decoded straight to greyscale.

## Impact

- Code: `detect.py` (coarse pass, `MarkerTracker`), `pipeline.py`
  (`detector=` per call, `session_detector()`, greyscale replay),
  `aim_hold.py` (passes the detector through), `marker_source.py`
  (per-session tracker, `tracked_detection` option), `server.py`
  (greyscale decode, `--full-frame-detection`).
- `detect_markers()` is unchanged, so every direct caller -- tests, the
  overlay checks, and the lens-calibration work landing between
  detection and solve -- sees the same corners in the same coordinates.
- Tests: new `tests/test_detect_tracking.py`, new benchmark script.
- No new dependencies, no wire-format change.
