## Why

The solver fits a homography to raw detected corners, which assumes a
pinhole camera. Phone wide-angle lenses and the ESP32-CAM's OV2640 lens
both have visible radial distortion, which bends straight edges and
pulls corners near the frame edge off where a pinhole would put them. The
homography absorbs that error, and it skews the aim point most where
the markers sit near the edge of the frame. Both `detect.py`'s docstring
and the `improve-marker-detection` design name `undistortPoints` as the
missing step. It needs per-camera intrinsics, and nothing measures those
yet.

## What Changes

- Serve a ChArUco calibration board from the existing `/markers`
  routes: a vector SVG (`/markers/charuco.svg`) and a page to print or
  show full-screen (`/markers/charuco`). The board uses a different
  ArUco dictionary from the aim markers, so the aim detector never reads
  it as a layout tag.
- Add lens calibration from a live session. Calibration is started for
  one streaming session from the phone UI (a "Calibrate lens" button,
  sent as a control message on the frame socket) or, for a client with
  no screen such as the ESP32-CAM, by `POST /calibration` naming the
  session. The server takes varied views of the board from that
  session's own frames. Once it has enough, it runs ChArUco calibration
  and reports the RMS reprojection error. It stores the camera matrix
  and distortion coefficients under `.boresight/lenses.json`, keyed by
  client kind, camera name (when the client reports one) and frame
  resolution. `GET /calibration` lists what is stored.
- Apply a stored calibration. When a session's frames match a stored
  key, the pipeline undistorts the detected marker corners
  (`cv2.undistortPoints` with `P = K`, so they stay in pixel units)
  before the homography. The image centre is undistorted the same way,
  so the aim point is still the point under the reticle. Debug geometry
  is distorted back into raw image pixels, so the overlay still matches
  the preview. The whole frame is never remapped.
- With no stored calibration for a session, every frame is processed
  exactly as it is today.
- The phone's `hello` may carry an optional `camera` label, so two
  phones' cameras (or one phone's two rear cameras) do not share a
  calibration.
- Out of scope: full 6-DoF `solvePnP` (future work, see design), fisheye
  lens models, and scaling a calibration to another resolution.

## Capabilities

### New Capabilities
- `lens-calibration`: the ChArUco capture and calibration of a
  session's camera, how it is triggered and reported, and how results
  are stored and looked up per client, camera and resolution.

### Modified Capabilities
- `marker-generation`: adds the ChArUco calibration board SVG and page.
- `aim-pipeline`: the per-frame operation accepts an optional lens model
  and undistorts corners and the aim pixel with it. Debug geometry stays
  in raw image pixels.
- `homography-solve`: the solver can be given the image-plane point to
  aim through, which defaults to the image centre as today.
- `video-ingest`: sessions apply their stored lens, accept the
  `calibrate` control message and the `camera` field of `hello`, and
  report calibration progress in their telemetry.
- `phone-client`: a calibrate button, calibration status, and the
  camera label in `hello`.

## Impact

- New modules `src/boresight/lens.py` (lens model, undistort/distort,
  JSON store) and `src/boresight/calibration.py` (board, capture,
  calibration).
- `markers.py` (board routes), `solve.py` (optional aim pixel),
  `pipeline.py`, `aim_hold.py` and `marker_source.py` (pass the lens
  through), `server.py` and `stream.py` (session wiring, routes,
  telemetry), `web/` (button and status).
- `detect.py` is not touched. No new dependencies:
  `cv2.aruco.CharucoDetector` and `CharucoBoard.matchImagePoints` exist
  from OpenCV 4.7, and the floor is 4.10.
- New on-disk state: `.boresight/lenses.json`. `.boresight/` is already
  git-ignored.
