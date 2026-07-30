## 1. Dependencies

- [x] 1.1 Add `opencv-python-headless` and `numpy` to `[project]
      dependencies` in `pyproject.toml`, `uv sync`
- [x] 1.2 Confirm `uv run ruff check .` and `uv run pytest` still pass
      with the new dependencies present but unused (sanity check before
      writing any code)

## 2. Stage 1 — synthetic geometry (TDD, no image, no detector)

- [x] 2.1 Write a synthetic-correspondence test fixture: given a known
      3x3 ground-truth homography and the known screen-plane marker
      corners (mm), produce synthetic image-plane points by applying the
      homography
- [x] 2.2 Write the failing test: feed the synthetic correspondences
      into `solve.py`'s (not-yet-implemented) entry point, assert the
      returned aim point matches the point the ground-truth homography
      actually maps the image centre to, within a documented tolerance
- [x] 2.3 Write the failing test for insufficient correspondences (fewer
      than 4): assert a clear error is raised and `findHomography` is
      never reached
- [x] 2.4 Implement `src/boresight/solve.py`: accept a list of
      `(screen_point_mm, image_point_px)` correspondences, compute the
      image-plane -> screen-plane homography via `cv2.findHomography`
      (RANSAC, all correspondences), invert it, map the image centre
      through the inverse, return an aim point (plus homography and
      per-correspondence reprojection error, per design.md's Open
      Questions decision)
- [x] 2.5 Run the stage 1 tests, confirm they pass; tune tolerance
      constants against observed floating-point error and document them
      next to the assertions

      Both stage 1 tests passed on the first run at an `abs=1e-2` mm
      tolerance -- noise-free synthetic correspondences let
      `findHomography`'s least-squares refit recover the ground-truth
      homography to floating-point precision, no loosening needed.

## 3. Stage 2 — synthetic rendered image (TDD, real detector, no camera)

- [x] 3.1 Check whether `src/boresight/detect.py` exists and is usable;
      if not, implement the minimal ArUco detection wrapper needed for
      this stage (`cv2.aruco.ArucoDetector`, matching README's Pipeline
      section — detection through dictionary match only, no
      cornerSubPix/undistort refinement required for this change)

      `detect.py` did not exist; added `detect_markers()` wrapping
      `cv2.aruco.ArucoDetector` (`DICT_4X4_50`), returning marker
      id + 4 corners per detected marker.
- [x] 3.2 Write a synthetic-image fixture: render each marker (matching
      `markers.toml`'s layout) via `cv2.aruco.generateImageMarker` onto a
      blank canvas at its known screen-plane position, then warp the
      canvas with a known homography via `cv2.warpPerspective` to
      produce a synthetic "camera view" image
- [x] 3.3 Write the failing test: run the real detector against the
      rendered image to obtain image-plane corners, pair them with the
      markers' known screen-plane positions, feed the correspondences
      into `solve.py`, assert the returned aim point matches the known
      ground truth within a documented tolerance
- [x] 3.4 Run the stage 2 test against the stage 1 implementation of
      `solve.py`; fix any integration issues (e.g. correspondence
      ordering/ID-matching between detector output and marker config)
      without changing stage 1's passing behavior

      One integration fix: this OpenCV build (5.0.0) returns
      `detectMarkers`' `ids` as shape `(N,)` (scalar per marker), not
      the `(N,1)` shape older API docs/examples assume —
      `int(marker_id[0])` raised `IndexError`; fixed to `int(marker_id)`.
- [x] 3.5 Tune stage 2's tolerance separately from stage 1's — rendering
      and detection introduce additional numerical error beyond pure
      homography math — and document the chosen value

      Measured actual error before picking a number: ~0.6mm aim-point
      deviation, ~1.0px max per-corner reprojection error. Set tolerance
      to 1.5mm (~2-3x observed, margin without masking a regression).

## 3a. Stage 3 — end-to-end test against a realistic synthetic photo (added post-hoc)

No real camera/photo is available (markers aren't printed yet — see
README Milestones), so in place of a true e2e-on-a-real-image test,
`tests/test_solve_e2e_realistic.py` degrades stage 2's clean render with
the failure modes README's "Known failure modes" section names as
dominant — uneven exposure, blur, sensor noise — then runs the full
`detect_markers` -> `solve` pipeline against it end-to-end.

- [x] 3a.1 Implement the degradation step (lighting gradient, Gaussian
      blur, Gaussian noise) applied to stage 2's rendered/warped canvas
- [x] 3a.2 Write the end-to-end test: run detection + solve against the
      degraded image, assert the recovered aim point matches ground
      truth within a documented tolerance; assert at least one marker
      survives (the pipeline's actual floor — one marker's 4 corners are
      enough to solve), rather than asserting all 8 always do

      At this marker size (80px) and up to ~2.5x this degradation
      severity (checked by hand), all 8 markers kept decoding — ArUco
      turned out more robust to blur/noise/exposure than expected at
      this scale. The `>=1` assertion documents the pipeline's actual
      floor rather than overclaiming dropout this synthetic degradation
      doesn't reliably reproduce (real dropout needs occlusion/framing
      loss, out of scope for an image-level degradation model).
- [x] 3a.3 Tune the tolerance against observed error (measured ~1.3mm at
      seed=0, set to 3mm)
- [x] 3a.4 Pin the generated photo as a checked-in fixture instead of
      regenerating it in-memory per test run, so the e2e test is a true
      regression test — a code change in `detect.py`/`solve.py` that
      alters the result against this exact image is a real signal, not
      noise from a re-rolled random seed

      Added `tests/generate_synthetic_photo_fixture.py` (run manually,
      not part of the suite) writing `tests/fixtures/synthetic_photo.png`
      + `synthetic_photo.json` (ground-truth marker layout, homography,
      degradation params). Rewrote the test to load the fixture rather
      than generate it inline. PNG is ~1.3MB even at max compression —
      the injected noise defeats most of PNG's entropy coding; accepted
      as-is rather than adding complexity to shrink it further.

## 4. Verification

- [x] 4.1 Run `uv run pytest -v`, confirm all stage 1 and stage 2 tests
      pass with zero warnings

      7/7 passed (4 pre-existing cursor-injection tests + 3 new).
- [x] 4.2 Run `uv run ruff check .` and `uv run ruff format --check .`,
      confirm clean

      Fixed on the way: missing `zip(..., strict=True)` (B905) in
      `detect.py` and both new test files, and two lines over the
      88-char limit (E501), resolved via `ruff format`.
- [x] 4.3 Run `uv run pre-commit run --all-files`, confirm it passes

      All 6 hooks passed.

## 5. Documentation

- [x] 5.1 Update README.md: check off "Homography solve, print screen
      coordinates" under Milestones once this change is complete
- [x] 5.2 Add a short section (or extend "Running the server") noting
      `solve.py` exists as a standalone, camera-free module, is not yet
      wired into the server, and how to run its synthetic test suite

      Added "Homography solving (standalone)" section; also updated the
      "Running the server" intro and Repo layout note to mention
      `solve.py`/`detect.py`.
- [x] 5.3 Note in README or in this change's design.md follow-ups that
      real-time/video application of the solver (per-frame performance,
      frame-to-frame stability) is intentionally deferred to a future
      change, per this change's Non-Goals

      Covered in the new README section's last paragraph.
