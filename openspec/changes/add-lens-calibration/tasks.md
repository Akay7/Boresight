## 1. Lens model and store

- [x] 1.1 Add `src/boresight/lens.py`: `LensModel` (K, D, image size, RMS, views, created), `undistort_points`, `distort_points`, JSON (de)serialisation; verify a round trip distort→undistort returns the input within 0.01px in `tests/test_lens.py`
- [x] 1.2 Add `LensStore` (`.boresight/lenses.json`, key `kind|camera|WxH`, atomic replace, corrupt file → empty with a warning); verify persistence across instances, exact-resolution lookup and corrupt-file handling in `tests/test_lens.py`

## 2. Calibration board and capture

- [x] 2.1 Add `src/boresight/calibration.py` with the 7x5 `DICT_5X5_100` ChArUco board, its raster and a vector SVG built from the raster; verify the raster is fully detected by `CharucoDetector` and ignored by `detect_markers`, and that the SVG's rects reproduce the raster exactly
- [x] 2.2 Add `CalibrationCapture` (view acceptance, diversity rule, resolution reset, cancel, status) and `calibrate()` with `CALIB_FIX_K3` and the RMS bound; verify on synthetic views rendered through a known distorted camera that RMS < 1px and the recovered undistortion agrees with the true one within 1px, that a still board yields one view, and that a poor fit is not stored
- [x] 2.3 Serve `/markers/charuco.svg?width_mm=` and the `/markers/charuco` page from `markers.py`, and link it from the marker sheet; verify with route tests (SVG dimensions, 422 on non-positive width, link present)

## 3. Applying the calibration

- [x] 3.1 `solve(..., aim_px=None)`: map the given point instead of the image centre; verify the default is identical and an explicit point is mapped in `tests/test_solve.py`
- [x] 3.2 `AimPipeline.process_frame(..., lens=None)`: undistort corners and the image centre, and distort debug geometry back; pass `lens` through `HoldingPipeline` and `SessionPipeline`; verify on a synthetic layout image rendered with strong distortion that aim error with the lens is well below the error without it, that `lens=None` results are unchanged, and that the debug cursor lands on the image centre

## 4. Server and clients

- [x] 4.1 `hello` accepts `camera`; the session looks up its lens per frame by decoded size; telemetry carries `lens` and `calibration` only when relevant; verify in `tests/test_lens_calibration_server.py` that an uncalibrated session's telemetry is unchanged and a calibrated one reports `lens`
- [x] 4.2 `calibrate` control message and `POST /calibration` / `GET /calibration`; the capture runs on the session's executor thread and stores into the app's `LensStore`; verify start/cancel over the socket, HTTP 404/409 cases, the single-session default, and the listing
- [ ] 4.3 Phone UI: "Calibrate lens" / "Cancel" buttons, status row, board link, and `camera` in `hello`; verify by `node --check` on `capture.js` and by the served page containing the new controls

## 5. Docs and checks

- [ ] 5.1 README: a short "Lens calibration" section; verify it is present and brief
- [ ] 5.2 Run `uv run ruff check`, `uv run ruff format --check`, `uv run pytest -q` and `openspec validate --all --strict`, and verify all pass

## 6. Hardware (needs a device; not verifiable in CI)

- [ ] 6.1 Calibrate a real phone's rear camera from the phone UI with the board on a monitor and printed, and record RMS and the aim-error change at the frame edges
- [ ] 6.2 Calibrate an ESP32-CAM via `POST /calibration`, and tune `VIEWS_NEEDED` and the diversity threshold if capture is too slow or too easy
