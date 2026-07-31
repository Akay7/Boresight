## 1. Blender scene script (bpy, run inside Blender only)

- [x] 1.1 Build the marker canvas image (reuse
      `generate_synthetic_photo_fixture.py`'s approach: `MARKER_LAYOUT_MM`,
      `MARKER_SIZE_MM = 80.0`, `cv2.aruco.generateImageMarker` composited
      onto a blank canvas) as a standalone function callable before
      Blender is invoked
- [x] 1.2 Write the `bpy` scene script: create a plane at `z=0` sized to
      the canvas's physical (mm) extent, apply the canvas image as its
      texture; confirm Blender's default unit scale doesn't rescale
      geometry (1 Blender unit == 1mm, per design.md)
- [x] 1.3 Add a camera object with a small number of hand-picked keyframe
      poses (position + look-at target) forming a smooth sweep across the
      marker plane; zero any lens-shift/sensor-offset parameters (design.md's
      pinhole-assumption decision) so the principal point stays at the
      image centre
- [x] 1.4 Pick output resolution and camera distance/FOV so decoded
      marker cells stay comfortably above README's Sizing table minimum
      (~20px/cell) — verify against README's distance/FOV/resolution
      table, not just by eye
- [x] 1.5 For each frame: compute the ground-truth aim point analytically
      (camera `matrix_world` position + forward direction, ray-plane
      intersection with `z=0`) — independent of any `cv2.findHomography`
      call — and render the frame via Eevee to a raw-output directory
- [x] 1.6 Write raw ground truth (per-frame camera pose + computed aim
      point, marker layout, resolution) to a JSON file alongside the raw
      renders
- [x] 1.7 Run the scene script standalone
      (`blender-5.2 --background --python <script>`), render a handful of
      frames, eyeball them (marker patterns visible, camera path looks as
      expected) before wiring up the full fixture pipeline

## 2. Fixture generator driver (plain Python, invokes Blender as a subprocess)

- [x] 2.1 Write `tests/generate_synthetic_video_fixture.py`: invokes
      `blender-5.2 --background --python <scene_script> -- <args>` as a
      subprocess, pointing it at a temp output directory
- [x] 2.2 Load the raw rendered frames + ground-truth JSON back with
      `cv2`/`json`
- [x] 2.3 Apply the photo fixture's degradation model (uneven exposure,
      Gaussian blur, sensor noise) to each frame, seeded per-frame
      (`seed = base_seed + frame_index`) per design.md
- [x] 2.4 Write the final fixture: degraded frames to
      `tests/fixtures/synthetic_video/frame_XXXX.png` (max PNG
      compression, matching the photo fixture) and a combined
      `tests/fixtures/synthetic_video/manifest.json` (per-frame ground
      truth aim point, marker layout, degradation params, frame count)
- [x] 2.5 Discard the raw (pre-degradation) renders once the final
      fixture is written, per design.md's Open Questions resolution —
      confirm this during implementation rather than leaving temp files
      around
- [x] 2.6 Run the generator end to end, confirm
      `tests/fixtures/synthetic_video/` is populated with the expected
      frame count and a valid manifest

## 3. End-to-end test (TDD, no Blender at test time)

- [x] 3.1 Write the failing test `tests/test_solve_video_e2e.py` against
      the not-yet-generated fixture (confirms it fails on missing files,
      not a false pass)
- [x] 3.2 Implement: load `manifest.json` + all frames, run
      `detect_markers` -> `solve` per frame, collect the per-frame
      recovered aim points
- [x] 3.3 Assert per-frame accuracy: each frame's recovered aim point
      matches that frame's ground truth within a documented tolerance
      (measure actual error first, per this suite's established
      practice, before picking the number)
- [x] 3.4 Assert frame-to-frame coherence: for each consecutive frame
      pair, the measured aim-point delta matches the ground-truth
      aim-point delta within a documented tolerance (design.md's
      "compare deltas to known truth" decision, not an arbitrary jump
      threshold)
- [x] 3.5 Add the timing smoke check: measure wall-clock time to run
      `detect_markers` + `solve` across all fixture frames, assert total
      time under a generously-bounded ceiling chosen with margin over
      locally observed time; document it as a regression guard, not a
      real-time latency claim (design.md Non-Goals)
- [x] 3.6 Run the test suite, confirm it passes; tune tolerances against
      observed values and document them next to the assertions

## 4. Verification

- [x] 4.1 Run `uv run pytest -v`, confirm the new test passes alongside
      the full existing suite, zero warnings
- [x] 4.2 Run `uv run ruff check .` and `uv run ruff format --check .`,
      confirm clean
- [x] 4.3 Run `uv run pre-commit run --all-files`, confirm it passes
- [x] 4.4 Confirm the fixture PNGs are LFS-tracked (`git lfs ls-files`,
      `git check-attr filter -- tests/fixtures/synthetic_video/frame_0000.png`),
      per the existing `.gitattributes` `*.png` rule — no new LFS
      configuration should be needed
- [x] 4.5 Check total fixture size (`du -sh tests/fixtures/synthetic_video/`)
      against design.md's repo-size risk; reduce frame count/resolution
      if it's grown unreasonably large

## 5. Documentation

- [x] 5.1 Update README's "Homography solving (standalone)" section to
      mention the video end-to-end test and how to regenerate its
      fixture (`uv run python tests/generate_synthetic_video_fixture.py`,
      requires `blender-5.2`)
- [x] 5.2 Note that this change fulfills the "real-time/video
      application of the solver" follow-up `add-homography-solver`
      explicitly deferred — but that 1-euro filtering and server wiring
      remain separate, still-unbuilt milestones (design.md Non-Goals)

## 6. Implementation notes

Where the work diverged from the plan above, and why.

- **The scene became a TV, not a bare marker plane.** Tasks 1.1-1.4 as
  written reused the photo fixture's flat 800x800 square canvas. On
  review that was not the system being modelled: `markers.toml` puts the
  screen-mm origin at the top-left of the *active display area*, with
  markers on the bezel outside it (hence negative coordinates). The
  fixture is now a 16:9 panel (1220x686mm, README's worked example) with
  markers on white cardstock on the surrounding bezel, a colourful lit
  panel, and a dim colourful room behind — which also makes the fixture
  express README's dominant failure mode (bright screen beside dim
  paper) as explicit emission ratios rather than a clean render.
  Consequence: the photo fixture's layout is no longer shared, so the
  brief `render_marker_canvas()` extraction made for that sharing was
  reverted and `generate_synthetic_photo_fixture.py` is byte-identical
  to its committed state.

- **Two geometry bugs found by measuring rather than eyeballing**, both
  worth recording because both produced plausible-looking renders:
  1. `primitive_plane_add(size=1.0)` spans -0.5..+0.5, so scaling by 400
     yields a *400mm* plane, not 800mm — every canvas coordinate mapped
     to world at half scale. A centred, head-on test render passed
     anyway (scaling about the centre leaves the centre fixed), so this
     only surfaced once the camera aimed off-centre, as a doubled error.
     Aim error was ~70mm; it is ~0.8mm with the plane sized correctly.
  2. Markers flush against the canvas edge had no quiet zone: their
     black ArUco border ran into the dark background and the detector
     could not find the quad. Exactly the 5 markers touching x=0 or y=0
     failed. The photo fixture never hit this because
     `warpPerspective(borderValue=255)` supplies a white surround for
     free. Fixed physically rather than with a hack — the markers are
     printed on white cardstock, which *is* the quiet zone.
  Also: texture interpolation had to be `Linear`, not `Closest`; the
  canvas is minified and nearest-neighbour sampling aliased the bit
  cells apart.

- **Task 3.1's TDD ordering was not followed strictly.** The fixture had
  to exist before the test could be written, because the scene needed
  several iterations to get detection working at all. The property that
  task was protecting — that the test cannot pass without a real fixture
  — was verified afterwards by moving the fixture aside and confirming
  all four tests error out.

- **The test was mutation-tested**, which task 3.6 did not ask for but
  which is the only real evidence the assertions have teeth. Injecting a
  +6mm constant bias into `solve.py` failed the per-frame accuracy test
  and *not* the coherence test (correct: a constant bias does not change
  deltas). Injecting ±3mm alternating jitter — inside the per-frame
  tolerance, but 6mm frame-to-frame — failed the coherence test. So the
  two assertions genuinely measure different properties.

- **Frames are JPEG, not PNG** (task 3.2/4.5 assumed PNG). 20 noisy
  colour PNGs came to ~12MB, which is too much to check in; JPEG at
  q88 gives 2.5MB total. It is also what the phone client will actually
  stream per README's Software stack, so the compression artifacts are
  realistic rather than a concession. `.gitattributes` gained `*.jpg`
  and `*.blend` LFS rules alongside the existing `*.png`.

- **`scene.blend` is checked in** so the scene can be opened and
  inspected by hand, not only re-derived by running the script.

- **Measured against the final fixture** (tolerances set with ~3x
  margin): 7-8 of 8 markers detected per frame; per-frame aim error max
  1.54mm, mean 1.33mm on a 1220mm-wide panel (0.13%); consecutive-frame
  delta residual max 1.25mm against ground-truth steps of 43-135mm;
  detect+solve ~1.9ms/frame. Both fixtures were confirmed to regenerate
  bit-identically.

- **Still out of scope**, unchanged from design.md: 1-euro filtering,
  wiring into `server.py`, lens distortion/`undistortPoints`, and any
  claim about real camera behaviour or real-world latency (the timing
  check is a loose regression guard, not a latency claim).
