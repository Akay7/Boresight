## Context

`AimPipeline.process_frame` (`src/boresight/pipeline.py`) calls
`self._backend.move_absolute(*position)` only when a frame solves; on
any other outcome it emits nothing and returns. `MarkerSourceController`
(`src/boresight/marker_source.py`) already wraps the cursor backend once
in a `SmoothingCursorBackend` (`add-aim-smoothing`) and hands that same
wrapped backend to every `AimPipeline` it builds, including across a
marker-source switch. `controller.pipeline` is read fresh per frame by
`server.py`'s `process_loop` and passed straight to
`_decode_and_solve`, which calls `pipeline.process_frame(frame,
debug=...)` and nothing else — it has no reason today to know whether
the previous frame solved.

See proposal.md for why a silent cursor device reads as the OS pointer
going idle on this platform.

## Goals / Non-Goals

**Goals:**
- Keep the cursor backend receiving events through a short run of
  unsolved frames, without moving the cursor or changing what solving
  itself reports.
- Let a longer dropout go idle rather than freezing on a stale position
  forever.
- Compose around `AimPipeline` the same way `add-aim-smoothing` composed
  around `CursorBackend` — without adding state to `AimPipeline` itself.

**Non-Goals:**
- Exposing the hold window as a runtime/CLI setting. A fixed default,
  picked by feel during manual verification, same posture as
  `add-aim-smoothing`'s filter constants.
- Extrapolating or predicting a position during the hold — this only
  ever re-sends the last real solve, verbatim.
- Changing `FrameResult`, the wire message, or the debug overlay. A held
  frame's *reported* outcome is exactly its real one.

## Decisions

**A new wrapper composed around `AimPipeline`, not a change to it.**
Call it `HoldingPipeline`: constructed with an `AimPipeline` and the
`CursorBackend` to hold on (the same wrapped backend
`MarkerSourceController` already built), it implements the same
`process_frame(frame, *, debug=False)` signature. It delegates to the
wrapped pipeline, and on a non-`SOLVED` outcome within the hold window,
calls `backend.move_absolute(*last_position)` itself before returning
the wrapped pipeline's real (non-solved) `FrameResult` unchanged.
`AimPipeline` never sees this and stays exactly as stateless as its
spec requires.

Alternative considered: give `AimPipeline` a "repeat last position"
mode. Rejected for the same reason `add-aim-smoothing` rejected
filtering inside `AimPipeline` — it's temporal state the pipeline's own
spec says it must not hold, and every test asserting "processing the
same frame twice is identical" would need rethinking.

**`MarkerSourceController` builds one `HoldingPipeline` per
`AimPipeline`, at the same point it currently builds the pipeline.**
Unlike the `SmoothingCursorBackend` wrapper, which must survive a
marker-source switch, the hold state (last position, last solve time)
is naturally scoped to *this* pipeline's frames — a switch already
starts the new pipeline from a clean slate as far as holding is
concerned, which is correct: the previous source's last position has no
particular relevance to the new one.

**Re-sending the identical position is algebraically a no-op through the
filter, so this needs no coordination with `add-aim-smoothing`.** The
one-euro filter's low-pass step computes `alpha * value + (1 - alpha) *
previous`; feeding it a `value` equal to its already-converged
`previous` returns that same value for any `alpha`, regardless of the
`dt` the repeated call carries — up to ordinary floating-point rounding
in that arithmetic, orders of magnitude below anything visible or below
the edge-clamp margin `aim-pipeline` already applies. Holding therefore
cannot introduce a perceptible jump or fight the filter's own dropout
handling — it only produces device traffic.

**Hold window is a fixed duration, not a frame count.** Detection rate
varies with lighting and motion (README's own measured range), so a
frame-count budget would hold for a different real duration depending on
conditions. A wall-clock window (via the same monotonic-clock pattern
`add-aim-smoothing` uses) holds for the same real time regardless of
instantaneous frame rate.

**`controller.pipeline` now returns the `HoldingPipeline`, not the bare
`AimPipeline`.** `server.py` only ever calls `process_frame` on it, so
this is transparent to the serving path. Existing tests that reach
`controller.pipeline._map` or `controller.pipeline._backend` for
assertions need updating to go through the wrapper's own `._pipeline`
(the inner `AimPipeline`) where they want the inner pipeline's state;
`._backend` stays valid as-is, since the wrapper holds the identical
shared backend object.

## Risks / Trade-offs

- **A hold window picked wrong is either a shorter fix than the real
  idle-timeout (blinking continues) or long enough to misrepresent where
  aim currently is.** → Accepted for this change (Non-Goal: not
  runtime-tunable); picked by feel during manual verification against
  the actual compositor behavior, and easy to change later since it is
  one constant.
- **A trigger pulled deep into a held (not actually current) position
  fires somewhere the player is no longer aiming.** → Bounded by the
  same hold window: once it lapses, nothing is held, and within it the
  position held is only ever a few hundred milliseconds stale — the
  same staleness a player already accepts from the pre-existing
  "freeze in place on dropout" behavior this change extends, not new
  exposure.
