## Context

Each frame goes `detect_markers` → `AimPipeline.process_frame` → `solve`.
`solve` fits a screen→image homography to the raw corners and maps the
image centre `(w/2, h/2)` back through it. One `AimPipeline` is shared
by every session. Each session wraps it in its own `SessionPipeline`
(smoothing) and `HoldingPipeline` (dropout hold). The server decodes and
solves on executor threads, one frame in flight per session. Sessions
identify themselves with `hello` (`client`, `version`, `frame_size`).
`.boresight/` already holds the TLS material and is git-ignored.
Installed OpenCV is 5.0.0, and the floor is 4.10.

Another change is concurrently making detection faster in `detect.py`,
so this change leaves `detect.py` alone and puts undistortion in its own
step.

## Goals / Non-Goals

**Goals:**
- Calibrate from the exact frames the solver sees (same resolution,
  same JPEG path, same device), for the phone and the ESP32-CAM alike.
- Correct distortion at ~32 points per frame, never per pixel.
- Leave behaviour bit-for-bit unchanged with no calibration.

**Non-Goals:**
- Full 6-DoF `solvePnP`. With K and D known, `solvePnP` on the
  undistorted corners gives the pose, and the aim ray could then be
  intersected with the screen plane. For a planar target that is the
  same answer as the homography on undistorted points, apart from how
  noise is weighted. It becomes worth doing when something needs the
  pose itself, such as a boresight offset in 3D, parallax, or
  sparse-marker robustness. The `SPARSE_ERROR_IS_STILL_BAD_MM` test is
  still waiting on that. It is left as future work.
- Fisheye models (the OV2640 160° lens option) and rational models.
- Scaling a calibration to another resolution or crop. A phone may
  crop, not scale, between modes, so reusing a calibration at another
  resolution could silently be wrong.

## Decisions

### 1. Trigger: server-side capture from the live session, started from the phone UI or HTTP

The server takes the calibration views from the session's own decoded
frames. Two triggers call the same `start()`:

- the phone sends `{"type": "calibrate", "action": "start"|"cancel"}` on
  its frame socket, from a "Calibrate lens" button. The server already
  knows which session the socket belongs to.
- `POST /calibration {"address"?, "action"?}` covers screenless clients.
  The address is the one `GET /sessions` lists, and may be omitted when
  exactly one session is connected, which is the common ESP32 case
  (`curl -X POST .../calibration`).

*Alternative: a CLI that calibrates from image files.* It would need
its own frame source. The phone has no way to save frames, and the
record/replay work is a separate change. Photos taken another way
(camera app, other resolution, other processing) are not the frames
being solved, and that mismatch is exactly the error calibration must
avoid. The live path has no extra tooling and uses the right frames by
construction.

*Alternative: phone-only trigger.* It leaves the ESP32 uncalibratable.
The HTTP route is a few lines on top of the session registry.

### 2. Board: 7×5 squares, `DICT_5X5_100`, vector SVG derived from OpenCV's own raster

The aim markers are `DICT_4X4_50`. Using another dictionary means the
board never produces aim correspondences. It is checked by a test that
runs `detect_markers` on the board. The pattern comes from
`CharucoBoard.generateImage` at exact integer module sizes (72px
squares, 56px = 7×8px markers, 8px inset), so every edge falls on a
whole pixel. Runs of black pixels are then emitted as SVG `<rect>`s.
This keeps whatever square/marker convention OpenCV's detector expects
(the legacy-pattern question) instead of re-deriving it. Physical size
does not matter for intrinsics, so the board can be printed at any
scale or shown on a monitor. The page says so.

### 3. View selection and calibration

A frame is kept as a view when at least half of the board's 24 inner
corners are detected and not collinear. It must also differ from every
kept view: either the mean displacement of shared corner IDs exceeds 5%
of the image width, or fewer than half its corners are shared. This is
deterministic and cheap, and it stops a board held still from filling
all views with one pose. After `VIEWS_NEEDED = 20` views, the server
calls `cv2.calibrateCamera` on `board.matchImagePoints` output, with
`CALIB_FIX_K3`. Ported from `calibrateCameraCharuco`, which OpenCV 4.7+
no longer offers.

- `CALIB_FIX_K3`: in the prototype (25 synthetic views, true
  k1=-0.30, k2=0.10), a free k3 fitted k2=0.40, k3=-0.83. That
  correlated triple has the same RMS but extrapolates badly past the
  outermost views. Fixed k3 gave k1=-0.313, k2=0.165. Phone main and
  wide cameras, and the OV2640's standard lens, are well within a
  k1/k2/p1/p2 model.
- The calibration runs on the session's executor thread, inside the
  frame that completes capture (~15ms for 20 views). That stalls one
  frame of one session, which is not worth a separate task.
- It is accepted when RMS ≤ `MAX_RMS_PX = 1.5`. Real phone
  calibrations are typically 0.2–0.8px. Above 1.5 the views were
  blurred or the board was not flat, and storing that would make aim
  worse than no calibration.

### 4. Applying it: `lens.py`, corners and aim pixel both through `undistortPoints(P=K)`

`AimPipeline.process_frame(frame, *, lens=None, ...)`. With a lens,
each detected corner goes through `cv2.undistortPoints(pts, K, D, P=K)`
(iterative, 20 iterations / 1e-6, instead of the default 5 so strong
edge distortion converges). The image centre goes through the same
call, and `solve(..., aim_px=...)` maps that point instead of `(w/2,
h/2)`.

- **Undistorted centre, not the principal point.** The phone draws its
  reticle at the frame centre, and the spec says the aim is what is
  imaged there. Undistorting that pixel keeps the claim exact. Using
  `(cx, cy)` would move the aim by the principal-point offset (often
  10–30px), which is a boresight question the aim-offset calibration
  owns.
- **Per call, not per pipeline.** The pipeline is shared by sessions
  with different cameras. The same argument already applies to `debug`
  and `backend`.
- **Debug geometry** stays in raw pixels. Marker corners are reported
  as detected. The projected screen quad and cursor are distorted back
  with `cv2.projectPoints` on the normalised rays (`K⁻¹·p`, R=0, t=0),
  so the overlay still matches the preview and an unclamped cursor
  still lands on the reticle. Reprojection errors are in undistorted
  pixels, which is essentially the same scale.

### 5. Storage and lookup

`LensStore` holds one JSON file, `.boresight/lenses.json`, as
`{key: {camera_matrix, dist_coeffs, image_size, rms_px, views,
created}}`. The key is `"<client kind>|<camera label>|<W>x<H>"`, with an
empty camera label when none was given. It is read once at startup and
written with write-temp-then-replace under a lock. A calibration made in
one session is visible to every later lookup at once. Lookup happens
per frame against the decoded frame's size, which is authoritative:
`hello`'s `frame_size` is what the client asked for, and the frame is
what arrived. A corrupt file logs a warning and is treated as empty.

The phone adds `camera: track.label` to `hello`. Without it, two
phones (or one phone's main and wide rear cameras) would share a key.
The ESP32 has one camera and does not need it, so the firmware is
unchanged.

### 6. Telemetry

A session gets `calibration` in its stats (`state`, `views`,
`views_needed`, `rms_px`, `detail`) only once calibration has been
started in it. It gets `lens: {rms_px}` only when a lens was applied.
With neither, the message is byte-identical to today's, in keeping with
"telemetry is unchanged for sessions that do not ask".

## Risks / Trade-offs

- [Views too similar, for example all fronto-parallel, give a poorly
  constrained focal length] → The page asks for tilted views that cover
  the frame edges. The 5% displacement rule only enforces different
  positions. RMS does not detect poor coverage. A coverage indicator is
  possible follow-up work.
- [Autofocus or zoom changes intrinsics between calibration and play]
  → Phones refocus. Focus breathing changes f by ~1%, which moves aim
  only through the undistortion, a second-order effect. It is
  documented, not solved.
- [A calibration at 1280×720 no longer applies after the browser grants
  another size] → No lens is applied, which is exactly today's
  behaviour. Nothing gets worse silently.
- [Wrong or stale calibration makes aim worse] → The RMS bound, a
  per-key replace, and the file is plain JSON that can be deleted.
- [Board shown on a monitor with a refresh or moiré pattern] → The
  capture rejects frames with too few corners, so a bad frame costs
  only time.

## Migration Plan

None. Without `.boresight/lenses.json` nothing changes. To roll back,
delete the file.

## Open Questions

- Whether `VIEWS_NEEDED = 20` and the 5% threshold are right on real
  hardware. They are to be tuned on a phone and an ESP32-CAM (hardware
  tasks in tasks.md).
