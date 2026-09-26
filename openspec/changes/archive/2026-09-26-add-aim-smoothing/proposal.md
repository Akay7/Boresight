## Why

Every frame's solved aim point is emitted to the cursor immediately and
unfiltered, so ordinary per-frame detection noise — a marker corner
wobbling by a pixel, RANSAC picking a slightly different subset — shows
up directly as visible dribble in the cursor while the player is holding
aim on a target, making it hard to judge exactly where a shot will land.
This is a known, already-anticipated gap: `aim-pipeline`'s own spec
calls the pipeline "stateless" by design and explicitly defers holding
and smoothing a position to "the filtering stage," and README's
milestones list `1-euro filter tuning` as not yet done. Real-device
testing on the trigger and marker-source-control changes has now made
the gap concrete enough to fix.

## What Changes

- Add a one-euro filter (Casiez et al.) applied to the normalized aim
  position before it reaches the OS cursor: heavy smoothing while the
  aim point moves slowly (steady aim), little to no added lag when it
  moves quickly (a fast swing to a new target).
- The filter lives in a new `CursorBackend` decorator, not inside
  `AimPipeline` — `AimPipeline` stays exactly as stateless as its spec
  already requires. The decorator wraps whatever backend
  `MarkerSourceController` would otherwise hand to an `AimPipeline`, so
  every `AimPipeline` built across a marker-source switch shares the
  same filter state and the aim stays continuous across the switch
  (matching the existing "no reconnect, aim stays correct" requirement
  for source switching).
- The manual `POST /cursor/move` endpoint is unaffected: it keeps using
  the raw, unwrapped backend, since an explicit requested coordinate
  should land exactly, not be smoothed toward.
- The on-screen trigger's click needs no change: it already fires at
  wherever the last `move_absolute` call left the cursor, which will
  now be the filtered position — click and visible cursor stay in
  agreement automatically.
- Filter timing uses real elapsed time between solved frames, not a
  fixed frame rate, since Wi-Fi frame delivery jitters and frames can be
  dropped; a gap (e.g. across a period with no markers detected) is
  treated as a fresh sample rather than something to catch up smoothly
  toward.
- The filter's two tuning constants (minimum cutoff frequency, speed
  coefficient) get sane defaults tuned by feel during manual
  verification; not exposed as a runtime setting in this change.

## Capabilities

### New Capabilities
- `aim-smoothing`: temporal smoothing of the aim-derived cursor
  position between when `AimPipeline` solves a frame and when the
  position reaches the cursor backend, including its behavior across
  marker-source switches and across dropout.

### Modified Capabilities
(none — `aim-pipeline` keeps emitting a raw, unfiltered position per
frame exactly as its spec already requires; smoothing is a layer
composed around it, not a change to it)

## Impact

- `src/boresight/inject.py`: new `SmoothingCursorBackend` (or similar)
  implementing `CursorBackend`, wrapping another `CursorBackend`.
- `src/boresight/marker_source.py`: `MarkerSourceController` wraps the
  backend once at construction (not per switch) and passes the wrapped
  backend to every `AimPipeline` it builds.
- `src/boresight/server.py`: no change to the `/cursor/move` route —
  it keeps the unwrapped backend from `app.state.cursor_backend`.
- No change to `AimPipeline`, the WebSocket wire format, or the phone
  client.
