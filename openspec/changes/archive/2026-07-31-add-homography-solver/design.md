## Context

`markers.toml` (README.md "markers.toml") defines each marker's known
position in screen millimetres, origin top-left of the active display
area. The detector (existing/planned `detect.py`) produces, per visible
marker, an ID and four image-plane pixel corners. The Pipeline section
of README.md already commits to the algorithm: `findHomography` with
RANSAC over all correspondences, invert, map the image centre through
the inverse to get the aim point in screen space. This change builds
that step as a standalone, camera-free module, and establishes the
synthetic-data testing pattern the rest of the vision pipeline will
reuse: geometry-only synthetic correspondences first, then a rendered
synthetic image that exercises the real detector, before any real
camera or video is involved.

## Goals / Non-Goals

**Goals:**
- `solve.py` computes a screen-space aim point from a set of marker
  correspondences (screen-plane mm from `markers.toml`, image-plane
  pixels from a detector), using `findHomography` + RANSAC + inverse
  mapping of the image centre, per README's Pipeline section.
- Stage 1 test suite: pure synthetic geometry. A known ground-truth
  homography (or an equivalent known camera-like projection) generates
  synthetic image-plane points from the known screen-plane marker
  corners; `solve.py` must recover the known aim point within a defined
  pixel/mm tolerance. No image pixels, no detector, no camera.
- Stage 2 test suite: synthetic rendered image. Marker patterns are
  drawn into a blank canvas and warped by a known perspective transform
  (`cv2.warpPerspective`); the project's real detector runs against that
  rendered image to produce corners; `solve.py` consumes those detected
  corners and must recover the same known aim point within tolerance.
  This is the first test that exercises detection and solving together,
  without a camera.
- Establish the synthetic-fixture pattern (ground-truth transform in,
  tolerance-bounded assertion out) as the project's TDD approach for
  camera-free vision-pipeline modules going forward.

**Non-Goals:**
- Real-time/video application of the solver — running it per-frame
  against a video stream, performance budget, and frame-to-frame
  stability are a later change once a live video source exists
  (README's "Web server: phone connects over Wi-Fi, streams video"
  milestone is not built yet). Flagged as an explicit follow-up below,
  not solved here.
- Building or changing `detect.py`'s detection logic. Stage 2 depends on
  a working detector existing; if it doesn't yet exist in a usable form,
  this change implements the minimal synthetic-image detection call
  needed for the test, not a general-purpose detector.
- Camera intrinsics / lens distortion (`undistortPoints`) — README's
  Pipeline lists this as a separate step before `findHomography`. Out of
  scope; `solve.py` takes already-undistorted image-plane points as
  input.
- Wiring `solve.py` into `server.py` or any live endpoint. There is no
  detection/video source in the running server yet to feed it from.
- Multi-monitor / non-planar screen geometry — single flat display,
  consistent with `init-server-cursor-injection`'s existing Non-Goal.

## Decisions

**Module boundary: `solve.py` takes correspondences, not config files.**
`solve.py`'s entry point accepts a list of `(screen_point_mm,
image_point_px)` pairs (or ID-keyed dict) and the image dimensions, and
returns the aim point plus the homography used. It does not read
`markers.toml` or call the detector itself. Rationale: keeps the module
pure and trivially testable with synthetic data — callers (the future
real-time pipeline, or the stage-1/stage-2 test fixtures) are
responsible for assembling correspondences from whatever source
(config file + detector, or synthetic ground truth).
Alternative considered: have `solve.py` own config loading. Rejected —
that couples a pure geometry module to file I/O and would force stage-1
tests to go through disk, for no benefit.

**Stage 1 synthetic correspondences: generate via a known homography,
not a simulated camera pose.** Picking a 3x3 homography directly (e.g.
composed from a modest rotation/translation/scale) and applying it to
the known screen-plane marker corners is sufficient to exercise
`findHomography`'s recovery and the inverse-mapping math, and is far
simpler than simulating a pinhole camera + extrinsics. Rationale: stage
1 is testing `solve.py`'s math, not a camera model; a full camera
simulation belongs to stage 2 (via `cv2.warpPerspective`, which is
itself just a homography applied to pixels) if not later.
Alternative considered: derive synthetic points from a simulated
`cv2.projectPoints` camera pose. Rejected for stage 1 as unnecessary
complexity — deferred to stage 2's rendered-image approach, which
already implicitly encodes a projective transform via
`warpPerspective`.

**Stage 2 synthetic image: `cv2.warpPerspective` of rendered ArUco
tags, not a 3D-rendered scene.** Draw each marker (via
`cv2.aruco.generateImageMarker`, matching README's marker generation
tool) onto a blank canvas at its known screen-plane position, then warp
the whole canvas by a known homography to simulate a camera view.
Rationale: this produces real pixel data the real detector must
actually decode (dictionary match, corner extraction), unlike stage 1,
while staying fully deterministic and hardware-free — no lens model,
lighting, or noise simulation needed yet. Corner/reprojection tolerance
in the assertion absorbs the small numerical error `warpPerspective`
and detection introduce.
Alternative considered: skip stage 2 and rely on stage 1 plus real
hardware testing later. Rejected — stage 2 is what actually proves
`solve.py` and `detect.py` compose correctly, matching how
`init-server-cursor-injection` also included an image/device-level
manual verification step, not just unit-level fakes.

**New dependency: `opencv-python-headless`, not `opencv-python`.**
The server has no GUI/display requirement (`cv2.imshow` etc. are
unused); the headless wheel avoids pulling in GTK/Qt system libraries
this project doesn't need, matching the "smallest slice" precedent set
by the previous change's dependency choices.

**Tolerance-bounded assertions, not exact-equality.**
Both stages assert the recovered aim point (and/or homography) is
within a small pixel/mm tolerance of ground truth, not bit-exact —
`findHomography`'s RANSAC and floating-point warping are not exact
inverses. Exact thresholds are chosen during implementation and
documented next to the assertions.

## Risks / Trade-offs

[Stage 2 depends on a working detector; if `detect.py` doesn't exist yet
as usable code, this change may need to implement a minimal detection
call itself] → Check `src/boresight/` at implementation time; if
`detect.py` is missing, add the smallest possible ArUco detection
wrapper (`cv2.aruco.ArucoDetector`, per README's Pipeline) as part of
this change rather than blocking on a separate one, and note that in
tasks.md.

[Synthetic image tests (stage 2) are not a substitute for real-camera
validation — real lenses have distortion, blur, and exposure problems
none of this synthetic pipeline models] → Acceptable; this change's
purpose is proving the geometry/detection composition is correct, not
validating real-world robustness. README's existing "Testing" section
(recorded 30s capture fixture) remains the plan for that, unchanged by
this change.

[`RANSAC` introduces run-to-run nondeterminism in principle] → Seed
`cv2.setRNGSeed` or accept `findHomography`'s default (typically stable
for well-conditioned, low-noise synthetic correspondences); if flakiness
appears during implementation, pin a seed and note it in tasks.md.

[Real-time/video use is explicitly deferred — someone building the next
change has to re-derive the performance requirements] → Captured as a
named Non-Goal above and should become its own change once a video
source exists; not tracked further here.

## Migration Plan

Greenfield — no existing `solve.py` or consumer of it. Implementation
order: stage 1 tests + `solve.py` core (TDD: write the synthetic-geometry
test first, watch it fail with no implementation, then implement).
Stage 2 tests follow once stage 1 passes, adding the rendering fixture
and (if needed) minimal detection wiring. No deployment or rollback
concerns — nothing consumes this module yet.

## Open Questions

- Exact tolerance values for stage 1/stage 2 assertions (pixels for
  image-plane checks, mm for screen-plane aim-point checks) — pick
  concrete numbers during implementation based on observed
  `warpPerspective`/detection error on the synthetic fixtures, document
  them in code comments next to the assertions.
- Should `solve.py` return just the aim point, or also the homography
  matrix and per-correspondence reprojection error? README's later
  milestone "Debug overlay with per-frame reprojection error" will need
  the latter — leaning toward returning a small result object
  (aim point + homography + reprojection errors) now so that milestone
  doesn't require reshaping this module's API. Confirm during
  implementation.
- Real-time/video follow-up change is intentionally not scoped here;
  revisit once the phone/video-streaming milestone lands.
