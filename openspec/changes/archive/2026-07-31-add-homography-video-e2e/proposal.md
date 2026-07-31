## Why

`add-homography-solver` (archived) deliberately deferred real-time/video
application of `solve.py` as an explicit Non-Goal: "running it per-frame
against a video stream, performance budget, and frame-to-frame stability
are a later change once a live video source exists." There's still no
real camera or video-streaming server, so this change does for video
what that change did for a single photo: generate the closest available
synthetic substitute, pin it as a checked-in fixture, and run the full
`detect_markers` -> `solve` pipeline against it end to end, frame by
frame, to validate accuracy and frame-to-frame stability before any real
video source exists.

Unlike the single-photo fixture (a 2D canvas warped by one hand-picked
homography), a *video* needs a physically coherent moving camera across
many frames — approximating that by linearly interpolating homography
matrix entries frame-to-frame would produce a plausible-looking but
non-physical camera path. Blender (available in this environment,
`blender-5.2`) renders an actual pinhole camera moving through a real 3D
scene, giving each frame a true perspective projection and, crucially, an
independent ground-truth aim point computed analytically from the
camera's known 3D pose (ray-plane intersection) — not derived from the
same homography math `solve.py` itself uses, so the test doesn't just
check that `solve.py` agrees with itself.

## What Changes

- Add a Blender-driven fixture generator (`tests/generate_synthetic_video_fixture.py`
  driving a `bpy` scene script via `blender-5.2 --background --python`):
  builds a 3D scene with the marker layout textured onto a screen-plane,
  animates the camera through a smooth sweep across N keyframed frames,
  and renders each frame to PNG. Blender is a fixture-generation-time
  tool only — regenerating the fixture requires it, running the test
  suite (`pytest`) does not.
- Per frame, compute the ground-truth aim point analytically from the
  camera's Blender-space transform (independent of `solve.py`'s own
  homography math) and record it, alongside marker layout and generation
  parameters, in a checked-in manifest.
- Apply the same post-render degradation `add-homography-solver`
  introduced for its photo fixture (uneven exposure, blur, sensor noise)
  to each frame, per-frame-seeded for determinism.
- Pin the rendered, degraded frame sequence and manifest as checked-in
  fixtures under `tests/fixtures/synthetic_video/` (PNG frames already
  covered by the repo's `.gitattributes` LFS rule).
- Add an end-to-end test that runs `detect_markers` -> `solve` against
  every fixture frame and asserts: (a) each frame's recovered aim point
  matches that frame's ground truth within a documented tolerance, and
  (b) consecutive-frame aim points don't jump beyond what the known
  camera motion between those frames would produce — i.e. no
  reconstruction discontinuities the smooth input motion doesn't
  justify.
- Add a lightweight, generously-bounded per-frame timing check across
  the fixture sequence — a regression guard against a gross performance
  bug, not a real-time latency claim (README's own Network section says
  actual round-trip latency has to be measured against real hardware,
  not synthesized).
- Out of scope: 1-euro filtering (a separate, still-unbuilt README
  milestone), wiring `solve.py` into the FastAPI server, and any claim
  about real camera/lens behavior (motion blur here is Blender's
  render-time approximation plus post-process blur, not a physically
  simulated shutter).

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `homography-solve`: adds a requirement that per-frame solver output,
  when applied independently to each frame of a temporally coherent
  sequence, itself forms a temporally coherent trajectory (no
  unjustified frame-to-frame discontinuities) — a property not
  guaranteed by the existing single-frame requirements, which only
  specify one call's correctness in isolation.

## Impact

- New code: `tests/generate_synthetic_video_fixture.py` (Python driver)
  plus a Blender scene-construction script it invokes via
  `blender-5.2 --background --python`.
- New checked-in fixtures: `tests/fixtures/synthetic_video/frame_*.png`
  (LFS, via the existing `.gitattributes` `*.png` rule) and
  `tests/fixtures/synthetic_video/manifest.json`.
- New test: `tests/test_solve_video_e2e.py`, exercising the existing
  `detect.py`/`solve.py` unchanged — no changes to their public API.
- New environment dependency for fixture *regeneration* only: Blender
  (`blender-5.2`, already installed in this environment). Not a
  `pyproject.toml` dependency and not required to run the test suite,
  matching the fixture-generator-is-dev-only precedent
  `generate_synthetic_photo_fixture.py` already set.
- No changes to `server.py`, `inject.py`, `solve.py`, or `detect.py`.
