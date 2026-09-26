## Why

The aim point is the image centre pushed through the solved homography,
with no correction. A camera is never mounted exactly along the barrel:
a 1° tilt is ~3.5 cm off at 2 m, and a camera a few centimetres beside
the sight line (parallax) adds its own offset. Light-gun games hide the
cursor, so the player cannot see the error to compensate for it — the
gun has to be zeroed, the way a real sight is.

## What Changes

- A zeroing step started from the phone: the screen shows one target at
  a time (the four corners and the centre, drawn by the on-screen
  overlay when it is running; the display's own corners otherwise), the
  player aims through the gun's sights and pulls the trigger at each.
  During zeroing the trigger records a shot and never clicks the game.
- Each shot pairs the frame it names with the target's known position.
  From the shots the server fits a correction modelled on the physics:
  a fixed image-space offset for angular misalignment (valid at any
  distance and pose), plus a camera-to-barrel parallax offset that is
  fitted only when the shots were taken from sufficiently different
  distances to tell the two apart.
- The correction is applied to the solved aim before the dropout hold
  and smoothing, so the cursor, held positions and shots fired at a
  named frame's aim all use the corrected aim.
- Zeroing is stored per client in `.boresight/zeroing.json`, keyed by an
  identity the client sends in its `hello` (the phone keeps a random id
  in local storage), so it survives server restarts. It can be reset.
- The phone gets a small zeroing panel; every stats message carries the
  session's zeroing state.

## Capabilities

### New Capabilities
- `boresight-calibration`: the zeroing flow (targets, shots, fit),
  the correction model and its application to the aim, per-client
  persistence and reset, and the zeroing state in session telemetry.

### Modified Capabilities
- `trigger-emission`: a trigger from a session that is zeroing records
  a calibration shot instead of clicking.
- `aim-pipeline`: the per-frame operation accepts a per-session aim
  correction and applies it before normalization and clamping.
- `marker-overlay`: the overlay draws a calibration target where the
  server asks, still transparent to input.
- `phone-client`: zeroing controls and prompts, and a persistent client
  id in the `hello`.

## Impact

- New `src/boresight/zeroing.py` (model, fit, targets, store, session
  flow) and `src/boresight/web/zeroing.js`.
- `pipeline.py`, `aim_hold.py`, `marker_source.py`: pass a per-session
  correction through; the overlay child gets a stdin command channel.
- `overlay/qt_backend.py`, `overlay/render.py`, `overlay/__main__.py`:
  draw a target on command.
- `server.py`, `stream.py`, `shot.py`: small hooks for the zeroing
  messages, shot diversion and telemetry.
- New state file `.boresight/zeroing.json`. No new dependencies.
