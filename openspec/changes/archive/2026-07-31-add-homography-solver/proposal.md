## Why

The next unbuilt link in Boresight's pipeline (README.md "Pipeline", and
the "Homography solve, print screen coordinates" milestone) is turning
marker corner correspondences into a screen-space aim point. Detection
(`detect.py`) and cursor injection (`inject.py`) already exist or are
scoped; the geometry step between them — `findHomography`, invert, map
image centre to screen space — does not. This step is pure math with no
hardware dependency, which makes it the cheapest possible place to
establish a synthetic-data, test-first workflow before the project takes
on a camera or video stream: known marker layout + known transform in,
assert the recovered aim point back out, no camera involved.

## What Changes

- Add `src/boresight/solve.py`: given marker correspondences (screen-plane
  positions from `markers.toml`, in mm, paired with detected image-plane
  corners), compute the screen-plane -> image-plane homography via
  `cv2.findHomography` (RANSAC, all correspondences), invert it, and map
  the image centre through the inverse to produce a screen-space aim
  point.
- Add `cv2` (`opencv-python-headless`) and `numpy` as runtime
  dependencies — first use of either in this project.
- Add a synthetic-geometry test suite (stage 1): pick a known
  ground-truth homography, warp known screen-plane marker corners into
  synthetic image-plane points, feed them through `solve.py`, and assert
  the recovered aim point matches ground truth within tolerance. No
  image, no detector, no camera.
- Add a synthetic-image test suite (stage 2): render ArUco markers into a
  blank canvas via a known perspective warp (`cv2.warpPerspective`), run
  the project's own detector against that rendered image to obtain
  corners, then run `solve.py` on the detected corners and assert the
  result matches the same ground truth. Links `solve.py` to real
  detection code through a synthetic-but-visually-real image, still with
  no camera or video involved.
- Out of scope: real-time/video application of the solver (per-frame
  performance and frame-to-frame stability), and any change to
  `detect.py`'s own detection logic — this change consumes detection
  output, it doesn't build it. See design.md Non-Goals.

## Capabilities

### New Capabilities
- `homography-solve`: computes a screen-space aim point from marker
  corner correspondences via homography, given a known marker layout and
  a set of detected (or synthetic) image-plane corners.

### Modified Capabilities
(none — `solve.py` is new code with no prior spec-level behavior)

## Impact

- New code: `src/boresight/solve.py`, plus synthetic-fixture helpers
  under `tests/` (a synthetic-correspondence generator for stage 1, a
  synthetic-image renderer for stage 2).
- New runtime dependencies: `opencv-python-headless` (`cv2`), `numpy`.
- New test-only surface, following the `FakeCursorBackend` precedent:
  synthetic ground-truth generators instead of a fake backend, since
  `solve.py` has no I/O to fake — its inputs already are plain data.
- No changes to existing code (`server.py`, `inject.py` are untouched;
  `solve.py` is not wired into the server in this change since there is
  no live detection/video source yet to feed it).
