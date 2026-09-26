## 1. Measure

- [x] 1.1 Add `tests/measure_detection_speed.py` (decode and detection time, coarse-pass count, markers found, corner deviation, ground-truth corner error, aim error; `--threads`) and verify it runs over every fixture
- [x] 1.2 Record full-pass, tracked, ROI-prototype and ArUco3 numbers in design.md and verify each adopted strategy is faster on at least one fixture with no lost detection

## 2. Detection

- [x] 2.1 Add `detect_markers_coarse()` (half-size search, full-resolution `cornerSubPix`) to `detect.py`, leaving `detect_markers()` unchanged; verify with a test that its photo corners stay within 0.8px of ground truth
- [x] 2.2 Add `MarkerTracker` (size gate, same-frame fallback, full pass every 10 frames, backoff after a miss); verify with tests for fallback, bounded discovery of a newly visible marker, ESP32 frames staying full-frame, 0.1px deviation on the phone fixture, and interleaved sessions

## 3. Plumbing

- [x] 3.1 `AimPipeline`: `detector=` per call, `session_detector()`, `tracking` option; `replay()` uses one per sequence and reads greyscale; verify with pipeline tests that a stub detector is never bypassed
- [x] 3.2 `HoldingPipeline` passes the detector through; `SessionPipeline` creates one per session and anew on a source switch; `MarkerSourceController(tracked_detection=)`; verify with marker-source tests
- [x] 3.3 Server decodes JPEG to greyscale and gains `--full-frame-detection` through `create_app`; verify the stream end-to-end tests still match replay

## 4. Wrap-up

- [x] 4.1 README: one short paragraph on tracked detection, the option and the benchmark script
- [x] 4.2 Verify `uv run ruff check`, `uv run ruff format --check`, `uv run pytest -q` and `openspec validate --all --strict` pass
