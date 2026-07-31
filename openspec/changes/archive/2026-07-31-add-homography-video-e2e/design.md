## Context

`add-homography-solver` (archived) built `solve.py` and validated it
against progressively more realistic synthetic inputs — pure geometry,
a rendered single image, a degraded single image — each pinned as a
checked-in fixture once generated, per the pattern established mid-change
(`tests/generate_synthetic_photo_fixture.py` ->
`tests/fixtures/synthetic_photo.png` + `.json`, LFS-tracked via
`.gitattributes`). It explicitly deferred the video case: applying
`solve.py` per-frame to a stream, and whether the resulting per-frame
aim points behave sensibly over time. There's still no camera, no video
streaming server, and no printed markers (README Milestones). Blender
(`blender-5.2`) is available in this environment and can render an
actual 3D scene with a moving pinhole camera, which is a better
foundation for a synthetic "video" than extending the single-image
approach (interpolating 2D homography matrix entries frame-to-frame) —
that would be a plausible-looking but non-physical camera path, whereas
Blender gives real perspective projection and, more importantly, a
camera pose independent of anything `solve.py` computes, from which
ground truth can be derived analytically rather than by construction of
the same homography math being tested.

## Goals / Non-Goals

**Goals:**
- A fixture generator (`tests/generate_synthetic_video_fixture.py`, plus
  a `bpy` scene script it drives via
  `blender-5.2 --background --python`) that builds a 3D scene — the
  marker layout textured onto a screen-plane — animates the camera
  through a smooth multi-frame sweep, and renders each frame.
- Ground truth for each frame computed analytically from the camera's
  Blender-space transform (a ray-plane intersection: the camera's
  forward ray through the marker-plane), independent of `solve.py`'s own
  homography-based estimate — a real cross-check, not a tautology.
- The same post-render degradation model `add-homography-solver`'s
  photo fixture introduced (uneven exposure, blur, sensor noise),
  applied per frame with per-frame-varied noise for a touch more
  realism than replaying identical noise on every frame.
- Rendered, degraded frames and their ground-truth manifest checked into
  `tests/fixtures/synthetic_video/` (PNG, already LFS-tracked).
- An end-to-end test running `detect_markers` -> `solve` on every
  fixture frame, asserting per-frame accuracy against ground truth *and*
  that consecutive-frame aim points track the known consecutive-frame
  motion (no unjustified jumps).
- A generously-bounded timing smoke check across the fixture sequence —
  a regression guard, not a real-time latency claim.
- Blender required only to *regenerate* the fixture, never to run the
  test suite.

**Non-Goals:**
- 1-euro filtering / temporal smoothing — a separate, still-unbuilt
  README milestone. This change tests the *unfiltered* per-frame
  solver output; filtering is deliberately out of scope so this change
  isolates "does the solver alone behave reasonably over time" from
  "does a filter smooth it further."
- Wiring `solve.py`/`detect.py` into `server.py` or a real video
  endpoint — no live video source exists yet.
- Physically simulating a camera shutter/rolling-shutter motion blur —
  the "blur" here is Blender's render plus a post-process Gaussian blur,
  same approximation the photo fixture used, not a modeled shutter.
- Claims about real camera/lens behavior (distortion, real sensor noise
  statistics) — synthetic degradation approximates failure modes
  qualitatively, per the photo-fixture precedent, not quantitatively.
- Portability to other Blender versions/engines — this targets the
  `blender-5.2` binary installed in this environment; the scene script
  may need adjustment for other majors' API changes.

## Decisions

**Scene units: 1 Blender unit == 1mm.** Matches `markers.toml`'s
existing screen-mm convention directly — marker layout coordinates,
camera position, and the ground-truth aim point are all the same
numbers Blender uses internally, no unit-conversion step to get wrong.

**Screen texture: reuse the existing canvas-rendering approach, one
textured plane.** Rather than placing 8 separate marker objects in the
3D scene, render the same kind of flat canvas
`generate_synthetic_photo_fixture.py` already builds (ArUco patterns via
`cv2.aruco.generateImageMarker`, composited at each marker's known mm
position) and apply it as a single image texture on one plane at
`z=0`. Reuses proven code, and keeps "where markers are" defined in one
place (a 2D canvas raster) rather than duplicated as two different
scene representations (2D canvas vs. 3D marker objects) that could
drift apart. Alternative considered: individual textured marker planes
in 3D. Rejected as unnecessary complexity — nothing in this change needs
markers to be independently occludable or non-coplanar.

**Marker layout reused verbatim from the photo fixture
(`MARKER_LAYOUT_MM`, `MARKER_SIZE_MM = 80.0`).** One less thing to
invent; keeps the two fixtures comparable if someone reads both.

**Ground truth computed by the Blender script, not the Python driver.**
The `bpy` scene script has direct access to the camera's
`matrix_world` each frame; it computes the ground-truth aim point itself
(camera position + forward direction, intersected with the `z=0`
marker plane) and writes it to a raw ground-truth JSON alongside the
rendered frames, before the pure-Python driver ever runs. The driver
(`generate_synthetic_video_fixture.py`, run with plain `uv run python`,
no `bpy` import) then only: invokes Blender as a subprocess, loads the
raw renders + ground truth back, applies post-render degradation, and
writes the final fixture. This keeps the `bpy`-dependent code isolated
to one small script that only ever runs inside Blender's interpreter.

**Pinhole assumption: zero lens shift, principal point at image
centre.** The ray-plane-intersection ground truth assumes the camera's
forward ray passes through the image centre — matching `solve.py`'s own
assumption (it maps the image centre through the inverse homography).
The Blender camera's lens-shift/sensor-offset parameters must stay at
their defaults (0) for this to hold; documented explicitly in the scene
script rather than left implicit, since Blender does allow shifting the
principal point off-centre.

**Camera path: two (or a few) hand-picked keyframe poses, Blender's
default interpolation between them.** Not a claim of matching a real
light-gun swing's kinematics — just enough motion, over enough frames,
to produce a non-trivial trajectory for the stability check. Distance
and marker size chosen to keep decoded marker cells comfortably above
README's Sizing table minimum (~20px/cell) at the fixture's output
resolution.

**Frame-to-frame stability assertion: compare measured consecutive-frame
deltas to ground-truth consecutive-frame deltas, not an arbitrary "jump"
threshold.** Reuses the same "compare against known truth within a
documented tolerance" pattern the rest of the suite already uses, rather
than inventing a separate jump-detection heuristic with its own
threshold to justify.

**Rendering engine: Eevee (Blender's default real-time engine), not
Cycles.** Faster in headless background mode; the projective geometry
this test relies on (perspective projection of a flat textured plane) is
identical between engines — only shading/lighting quality differs, which
this change doesn't depend on for correctness.

**Per-frame degradation reuses the photo fixture's model, seeded
per-frame.** `seed = base_seed + frame_index` (rather than one shared
seed for every frame) gives each frame slightly different noise, closer
to a real sensor across time, while staying fully deterministic and
reproducible.

## Risks / Trade-offs

[Blender is a heavy, non-`pyproject.toml` dependency] → Fixture is
checked in; regenerating it is the only path that touches Blender.
Documented explicitly (required version `blender-5.2`, exact invocation)
in the generator script's docstring and in README, matching how
`generate_synthetic_photo_fixture.py` is already documented as
dev-only/manual.

[`bpy` API surface differs across Blender majors; this script targets
5.2 specifically] → Not attempting cross-version portability; pin the
required version in documentation rather than defensive version-checking
code that would add complexity for a fixture-regeneration-only path.

[N video frames at fixture resolution could meaningfully grow repo
size, compounding the ~1.3MB single-photo fixture] → Keep frame count
and resolution modest (exact numbers decided during implementation,
balancing a meaningful trajectory against repo bloat); apply the same
max-compression PNG write the photo fixture uses. Accepted as a
continuation of the pin-fixtures tradeoff already made, not a new one.

[Eevee's rasterized rendering could subtly diverge from an ideal pinhole
projection at scene edges/extreme angles] → Low risk for this scene
(flat plane, moderate camera angles matching README's documented
FOV/distance ranges); if fixture generation shows detection/geometry
anomalies at the trajectory's extremes, narrow the camera path rather
than debugging Eevee's projection internals.

[Analytic ground truth and `solve.py`'s own math could share a
blind spot neither catches, since both ultimately model a pinhole
camera] → Acknowledged limitation, not fully mitigated: the ground
truth is independent of `solve.py`'s *implementation* (computed from raw
camera transform, not from any `cv2.findHomography` call), which does
catch homography-estimation bugs — but it can't catch an error in the
shared modeling assumption itself (e.g. if pinhole projection were the
wrong model for a future real camera). Out of scope to solve here.

## Migration Plan

Greenfield — no existing consumer of `solve.py`'s output depends on
per-frame behavior yet. Implementation order: build and manually verify
the Blender scene script in isolation first (render a handful of frames,
eyeball them, confirm marker decode works before wiring up the full
fixture pipeline); then the ground-truth computation; then degradation;
then the pinned fixture; then the end-to-end test (TDD: write it against
the not-yet-generated fixture, watch it fail on missing files, then run
the generator). No deployment/rollback concerns — purely additive test
coverage and fixture data.

## Open Questions

- Exact frame count and output resolution — decided during
  implementation, balancing trajectory expressiveness against repo size
  and Blender render time; resolution must stay comfortably above
  README's Sizing table's marker-decode minimum for the chosen
  distance/FOV.
- Exact tolerance values for per-frame accuracy and inter-frame delta —
  measured against the actual generated fixture and picked with margin,
  same approach used throughout this suite; not prescribed here.
- Whether to keep Blender's raw (pre-degradation) renders around
  on-disk for debugging fixture generation, or discard them once the
  final degraded fixture is written — leaning discard (keep the repo to
  one fixture per test, not two), confirmed during implementation.
