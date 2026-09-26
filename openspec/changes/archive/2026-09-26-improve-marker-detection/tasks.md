## 1. Measurement

- [x] 1.1 Add `tests/measure_detection.py`, comparing OpenCV-default
      detection (rebuilt per call) with `detect_markers` on corner error,
      aim error, frame-to-frame delta, marker count and ms/frame for
      synthetic_photo, synthetic_video, esp32cam_video and close_range;
      verify `uv run python tests/measure_detection.py` prints both runs
- [x] 1.2 Sweep refinement method and window (SUBPIX win/relative
      size, iterations, accuracy; CONTOUR; APRILTAG; downscaled frames)
      and record the table and chosen parameters in design.md; verify no
      fixture's max aim error is worse than unrefined under the chosen
      setting

## 2. Detector

- [x] 2.1 Enable `CORNER_REFINE_SUBPIX` in `detect.py` with the
      measured parameters as named constants; verify the corner error on
      synthetic_photo drops below 0.8px max
- [x] 2.2 Build the detector once per thread (`threading.local`)
      instead of per call, keeping `detect_markers(image)`'s signature;
      verify `pipeline.py` and every caller are unchanged and the suite
      passes

## 3. Tests

- [x] 3.1 Add `tests/test_detect.py`: corner accuracy against the
      photo's ground-truth homography, per-thread reuse, distinct
      detectors across threads, concurrent detection identical to
      sequential; verify `uv run pytest tests/test_detect.py` passes
- [x] 3.2 Tighten tolerances to ~2x the refined observed values
      (video e2e aim and delta, realistic photo, partial-visibility
      inside-hull and 4-corner bounds) and refresh observed-value
      comments (close_range, sparse single-marker); verify each tightened
      bound still passes, and that the delta/inside-hull/corner bounds
      would fail on the unrefined values recorded in design.md

## 4. Docs and gate

- [x] 4.1 Update README's description of `detect.py` (no longer "no
      cornerSubPix refinement") and the source-tree comment; verify by
      reading the rendered paragraph
- [x] 4.2 Run `uv run pytest -q`, `uv run ruff check`, `uv run ruff
      format --check` and `openspec validate improve-marker-detection`;
      all pass
