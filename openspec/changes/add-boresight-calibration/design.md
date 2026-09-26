## Context

`solve.py` fits a homography `H` (screen mm → image px) per frame and
returns `H⁻¹(image centre)` as the aim. `AimPipeline` normalizes and
clamps it; each session wraps the shared pipeline in its own dropout
hold (`HoldingPipeline`) and smoothing (`SmoothingCursorBackend`)
through `SessionPipeline`. A trigger naming a frame fires at that
frame's unsmoothed position, looked up in the session's `AimHistory`.
The on-screen overlay is a child process of the server that reports
its geometry on stdout and takes no input from anyone.

See proposal.md for why the aim needs correcting.

## Goals / Non-Goals

**Goals:**
- Correct angular misalignment and camera-to-barrel parallax with a
  model that stays valid when the player moves, not only at the pose
  the shots were taken from.
- Zero from the phone in under a minute, without clicking the game.
- Keep the correction per client and persistent across restarts.

**Non-Goals:**
- Lens distortion (the lens-calibration change covers it). Zeroing
  after lens correction lands is still valid; zeroing before and then
  enabling it shifts the image and needs a re-zero.
- Zeroing a client without a screen (ESP32-CAM) from another device.
  It can be keyed and stored, but nothing drives its flow yet.
- Correcting a mis-measured marker layout. That is a screen-space error
  the physical model deliberately does not absorb (see Decisions).

## Decisions

### 1. Model the error physically, in the camera image, not as a screen-space warp

A pinhole camera sees every ray in a fixed direction at a fixed pixel.
The barrel is such a direction, so pure angular misalignment means the
barrel aims at a fixed image point `c + δ` instead of the centre `c`,
whatever the distance or the angle to the screen. Parallax is a lateral
offset `t` between the camera and the barrel line; at depth `z` it
shows up in the image as `(f/z)·t`, so it shrinks with distance, while
on the screen it is a constant `t`.

So the barrel's image point is

    p = c + D·δ + k·t

with `D = diag(W, H)` (δ stored as a fraction of the frame, so a
resolution change with the same aspect keeps it), and `k` the local
image scale at the aim point in pixels per screen width, taken from the
frame's own homography as `sqrt(|det J_H|)·screen_width_mm`. `k` stands
in for `f/z` without knowing `f`: that is the one thing the homography
already measures. `t` is stored in screen widths so it means the same
thing against a printed layout (millimetres) and the overlay's (pixels
at scale 1). The corrected aim is `H⁻¹(p)`.

Alternatives considered:
- **Constant screen offset (1 shot) / affine or homography screen warp
  (≥3–4 shots).** Simple, and exact at the pose it was fitted at. But a
  tilt is an angle: its screen error grows with distance and changes
  with the viewing angle, so a screen-space fit made from the sofa is
  wrong standing up. With 6–8 parameters it also happily absorbs
  pose-dependent error and layout errors into a fixed map. Rejected.
- **Full 3D pose (`solvePnP`) with a barrel ray.** Exact, but needs the
  camera intrinsics, which Boresight does not have yet. The model above
  is its first-order form using only `H`.

### 2. Fit parallax only when the shots can tell it apart from tilt

Per axis the unknowns are `(δ, t)` with one equation per shot:
`W·δx + k·tx = p_target.x − c.x`. Shots from one distance all have
nearly the same `k`, so `δ` and `t` are collinear and the split is
noise. The fit therefore solves for `t` only when the shots' `k` spans
at least a factor `PARALLAX_MIN_SPREAD = 1.3` (about a 30% change of
distance); otherwise `t = 0` and `δ` is the mean offset — which is exact
at the zeroing distance and puts parallax's residual, `t·(1 − d/d₀)`,
at ~1.5 cm for a 3 cm offset zeroed at 2 m and played at 3 m. The flow
offers a last, optional shot "from a different distance" for players who
want the parallax term; everyone else still gets a correct zero at the
distance they play from.

`k` uses the geometric-mean scale of `J_H`, i.e. it assumes the camera
faces the screen. At 30° off-axis that misestimates `k` by ~7%, a 2 mm
error on a 3 cm parallax — below the solve's own noise.

The fit reports the RMS residual of the shots against their targets
(as a fraction of screen width), so a shot at the wrong target, or a
layout that is off, shows up as a number rather than as bad aim.

### 3. Apply the correction inside the per-frame solve, before hold and smoothing

`AimPipeline.process_frame` takes an optional `zero` argument, like
`debug` and `backend`: per call, so the shared pipeline stays stateless
and one session's zero never touches another's frames. The corrected
unclamped aim becomes `aim_point_mm`, then normalization and clamping
run as before. Doing it here rather than as a `CursorBackend` wrapper
means the clamp sees the corrected aim (an off-panel raw aim corrected
back onto the panel is not lost), and the reported position, the
dropout hold, smoothing, `AimHistory` and the debug `cursor_px` all see
the same corrected number. The debug reticle-vs-cursor gap then shows
the correction itself.

`SessionPipeline` holds the session's current `zero` and passes it per
frame. The frame result also carries the frame's `SightFrame`
(homography, image size, screen size; excluded from equality), which is
what a zeroing shot needs.

### 4. Shots go through the existing trigger queue, then divert

A zeroing shot is a trigger naming a frame, exactly like a real one, so
it reuses `_SessionTriggers`' ordering and "wait for the named frame"
logic. At the point where a press would claim the cursor and click, a
zeroing session instead hands the nearest solved frame's `SightFrame`
(from a second `AimHistory` of sight frames — made generic) to the
zeroing flow. It never claims the cursor, never presses, and `up` is a
no-op. A shot whose frame did not solve is reported as a miss and the
target stays.

### 5. Targets

With the overlay running, the targets are drawn by it: the four corners
of its available area inset by 15%, then the centre, then an optional
repeat of the centre "from a different distance". Inset keeps the
target inside the marker hull and off the tags. With printed markers
there is nothing to draw on, so the targets are the display's physical
corners, which the player can always see, then an optional repeat of the
top-left corner. Target positions are normalized full-screen
coordinates; each shot converts through its own frame's screen size, so
a marker-source switch mid-run does not corrupt the fit.

Only one session can zero at a time server-wide, since the overlay can
show one target.

### 6. Overlay command channel on stdin

The server starts the overlay with `--commands` and `stdin=PIPE` and
writes JSON lines: `{"target": [x, y]}` in full-screen pixels, or
`{"target": null}`. A reader thread queues them; a 50 ms Qt timer
applies them on the GUI thread. The target is drawn like a tag: an
opaque patch (white, black rings and crosshair) so it is visible over
anything, and the window stays input-transparent. Without `--commands`
stdin is not read, so a terminal-launched overlay is unchanged. A write
to a dead or restarted overlay is dropped quietly; the target is resent
on each step.

### 7. Per-client identity and storage

The key is the `hello`'s optional `id` (phone: random, kept in
`localStorage`), else the client kind, else `unidentified`. Ids are
restricted to `[A-Za-z0-9_-]{1,64}`. The store is a JSON file,
`.boresight/zeroing.json` next to the certificates, written atomically
(temp file + rename) and read once at startup; a corrupt file is logged
and treated as empty rather than failing the server.

### 8. Control messages

`{"type": "zeroing", "action": "start" | "finish" | "cancel" |
"reset"}` on the frame socket, alongside `debug`. `finish` fits and
saves from the shots so far (at least one); the flow also finishes by
itself after the last target, including the optional one. `cancel` keeps the previous zero. `reset`
deletes the stored zero and returns to the raw aim. Every stats message
carries `zeroing`: `{"active", "zeroed", "target": {label, index,
count, optional} | null, "shots", "message", "residual"}`.

## Risks / Trade-offs

- [Player shoots a target while not holding the gun still] → one shot
  per target, averaged by least squares; residual reported so a bad
  zero is visible and can be redone.
- [Aspect/resolution/lens change on the phone] → δ is stored as a frame
  fraction; an aspect change or a lens-correction toggle needs a re-zero.
  Documented in README.
- [Two phones share one kind-keyed zero when localStorage is
  unavailable] → acceptable fallback; the phone normally has storage.
- [The overlay restarts mid-zeroing (margin change)] → the next step
  resends the target; the current one can be re-shown by cancelling and
  restarting.

## Migration Plan

None: without a stored zero the aim is exactly as before. Rollback is
deleting `.boresight/zeroing.json` or pressing Reset.
