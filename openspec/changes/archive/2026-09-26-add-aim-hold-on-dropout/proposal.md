## Why

Real-device testing surfaced the OS cursor visibly blinking (disappearing
and reappearing) while aiming. `move_absolute` is only ever called on a
*solved* frame; any stretch with no solved frame — a marker briefly
occluded, motion blur, a partial view that fails to reach four
correspondences — goes completely silent on the cursor device. Wayland
compositors (this one included) hide an idle pointer after a period with
no input events, and a tablet-style pointer in particular relies on
periodic activity to stay shown as "in proximity." The result is a
cursor that blinks out and back every time detection has a rough patch,
which also means a trigger pulled during that gap fires at a position
the player can no longer see confirmed on screen. `pipeline.py`'s own
docstring already names this gap: "Holding the last good pose and
decaying it ... belongs to the filtering stage that lands on this seam
next" — the filtering stage now exists (`add-aim-smoothing`), and this
is the piece of it that change didn't cover.

## What Changes

- On a frame that does not solve, if a solved position was seen recently
  enough (within a fixed hold window), re-send that same position to the
  cursor backend — a fresh device event with no visible effect on cursor
  position, since feeding a one-euro filter the same value it already
  holds is a no-op regardless of elapsed time. This keeps the OS
  pointer's own idle/proximity timer from lapsing during an ordinary
  short dropout.
- Once the hold window elapses with no new solve, holding stops: the
  cursor is allowed to go idle (and, on this platform, disappear) rather
  than freezing indefinitely on a position that may no longer be where
  the player is aiming. This is the "decay" half of the pipeline
  docstring's phrase.
- The wire report and any debug overlay are unaffected: a held frame is
  still reported to the client exactly as its real (non-solved) outcome
  says, so `add-viewfinder-debug-overlay`'s already-verified "an unsolved
  frame carries nothing over" behavior does not change. Holding is a
  cursor-backend-only effect, invisible to the wire protocol.
- Lives as a new component composed around an `AimPipeline`, not inside
  it — `AimPipeline` keeps returning exactly what it solves, stateless,
  matching its existing spec. `MarkerSourceController` builds one such
  wrapper per pipeline and gives it the same shared cursor backend
  `add-aim-smoothing` already wires through a marker-source switch.

## Capabilities

### New Capabilities
- `aim-hold`: keeping the emitted cursor position alive on the backend
  through a brief run of unsolved frames, and letting it lapse once the
  gap outlasts a fixed hold window.

### Modified Capabilities
(none — `aim-pipeline` keeps its existing per-frame contract exactly;
`aim-smoothing`'s existing requirements are unaffected since holding
re-sends a value the filter treats as unchanged)

## Impact

- `src/boresight/pipeline.py` or a new module: a pipeline-level wrapper
  (not inside `AimPipeline`) that holds the last solved position and
  decides whether to re-emit it on a non-solved frame.
- `src/boresight/marker_source.py`: `MarkerSourceController` builds this
  wrapper around each `AimPipeline` it constructs, using the same shared
  cursor backend it already wires through `add-aim-smoothing`.
- No change to `server.py`'s wire report, debug overlay, or the manual
  `/cursor/move` route.
