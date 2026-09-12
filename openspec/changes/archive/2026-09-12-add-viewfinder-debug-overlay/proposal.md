## Why

Nothing on the phone says where the camera is actually pointing. The
aim point is defined as the image centre pushed through the inverse
homography (`solve.py`), but the preview is a bare video element with
no mark on it, so "the cursor is in the wrong place" is currently
indistinguishable from "the camera is not aimed where I think it is."
The two failure modes have opposite fixes and there is no way to tell
them apart, which makes every aiming problem a guess.

The check the operator actually wants to perform is a comparison: put
the reticle on a spot, look at the panel, and see whether the OS cursor
is on that same spot. That comparison is impossible today because half
of it — the camera's half — is invisible.

## What Changes

- Draw a reticle at the centre of the phone's preview, marking the one
  pixel the whole pipeline is built around. It needs no server data:
  the aim point *is* the image centre by construction, so the centre of
  the `<video>` element is exactly it, in every outcome including the
  ones that solve nothing.
- Add an opt-in debug overlay on top of the preview, drawn from
  geometry the server sends back per frame:
  - the detected marker quads and IDs, distinguishing tags the layout
    maps from tags it ignores — what the solve actually had to work
    with;
  - the screen rectangle projected through the solved homography into
    image space — if that outline hugs the real panel in the preview,
    the homography is right, and if it does not, the way it is wrong is
    visible rather than inferred;
  - the emitted cursor position pushed back through the same
    homography, which should land under the reticle. A visible gap
    between them is the normalize-and-clamp step disagreeing with the
    solve, which no existing number would reveal.
- Extend `AimPipeline.process_frame` with an opt-in per-frame debug
  result carrying that geometry in image pixels. Off by default; the
  solving path is unchanged when it is off.
- Carry the geometry in the existing telemetry message, only for a
  session that asked for it via a new `{"type": "debug"}` control
  message on the channel already reserved for control and telemetry.
- Add a debug toggle and a reprojection-error readout to the phone's
  existing telemetry panel.

## Capabilities

### New Capabilities

None. The reticle and overlay are display behaviour on an existing
client, the geometry is an output of an existing pipeline operation,
and it travels on an existing connection in an existing message.

### Modified Capabilities
- `aim-pipeline`: the per-frame operation gains an opt-in debug result
  reporting, in image-pixel coordinates, the detections it used, the
  screen rectangle under the solved homography, and the round trip of
  the emitted position back into the image — available on unsolvable
  frames too, where the detections are precisely what needs explaining.
- `video-ingest`: telemetry carries that geometry for sessions that
  request it through a new control message, and reports the solve's
  reprojection error. Sessions that never ask see an unchanged payload.
- `phone-client`: the preview carries a centre reticle whenever the
  camera is running, and an operator-toggled overlay drawing the
  server's geometry registered to the live image.

## Impact

- Changed code: `src/boresight/pipeline.py` (a `FrameDebug` result and
  a `debug` parameter on `process_frame`), `src/boresight/stream.py`
  (`SessionStats` carries the geometry and a debug flag; `as_message`
  emits the extra fields only when asked), `src/boresight/server.py`
  (`_handle_control` gains a `debug` case; the process loop asks the
  pipeline for debug output when the session wants it),
  `src/boresight/web/index.html` and `web/capture.js` (overlay canvas,
  reticle, toggle, readout).
- No new dependencies, no new endpoint, no wire-format change — the
  control message and the geometry both travel on the frame
  WebSocket's existing text channel.
- No change to solving, emission, or the cursor track. The debug path
  reads the homography `solve.py` already returns and never feeds
  anything back into the solve.
- Telemetry payload is additive and gated: a client that never sends
  the debug message receives byte-for-byte what it receives today.
