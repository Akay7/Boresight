## Context

`AimPipeline.process_frame` (`src/boresight/pipeline.py`) solves each
frame independently and calls `self._backend.move_absolute(*position)`
directly — the pipeline owns the `CursorBackend` and emits to it
inline, rather than returning a position for a caller to act on. Its
spec requires it to stay stateless and synchronous; holding or smoothing
a position across frames is explicitly out of its scope.

`CursorBackend` (`src/boresight/inject.py`) is already a small
`Protocol` (`move_absolute`, `click`) with two implementations
(`UinputCursorBackend`, `FakeCursorBackend`). `click()` fires at
whatever position the last `move_absolute` call left the cursor — it
carries no position of its own.

There is exactly one `CursorBackend` instance per server process
(`app.state.cursor_backend`), shared between the manual
`POST /cursor/move` route and `MarkerSourceController`, which passes it
to every `AimPipeline` it builds — including the fresh one built on
each marker-source switch. See proposal.md for why this matters (a
filter tied to an `AimPipeline`'s lifetime would reset on every switch).

## Goals / Non-Goals

**Goals:**
- Smooth aim-derived cursor movement without changing `AimPipeline`,
  the wire protocol, or the phone client.
- Keep filter state alive across a marker-source switch, since switching
  rebuilds the `AimPipeline` but should not discontinue smoothing.
- Keep the manual `/cursor/move` endpoint exact.

**Non-Goals:**
- Exposing the filter's tuning constants as a runtime/CLI setting.
  Fixed defaults, tuned by feel, for this change.
- Smoothing anything other than the two position axes — `click()` is
  unaffected and untimed by this change.
- Solving Wi-Fi latency/jitter measurement (separate, already-tracked
  milestone) — this change only makes the filter robust to uneven
  frame timing, not the transport that causes it.

## Decisions

**Smoothing lives in a `CursorBackend` decorator, not in `AimPipeline`.**
A class implementing `CursorBackend` wraps another `CursorBackend`:
`move_absolute` runs the incoming `(x, y)` through the filter and
forwards the filtered result; `click` passes straight through
unchanged. `AimPipeline` is constructed with this wrapper instead of
the raw backend and never knows smoothing exists.

Alternative considered: give `AimPipeline` optional filter state.
Rejected — it contradicts the pipeline's own stateless requirement,
would need to move or duplicate state across the "new pipeline per
switch" boundary in `MarkerSourceController`, and would smooth
`/cursor/move` calls too unless every call site were audited to keep it
out. The decorator sidesteps all three: it composes at the one existing
seam (`CursorBackend`) instead of adding a second.

**`MarkerSourceController` constructs the decorator once, at its own
construction, not per `AimPipeline` build.** It wraps the backend it is
given, and every `AimPipeline` it builds — including on a
marker-source switch — is built with that same wrapped backend. Filter
state therefore has the same lifetime as the controller (i.e. the
server process), not the currently-active pipeline.

Alternative considered: build a fresh filter alongside each new
`AimPipeline`. Rejected — this is what would reset smoothing on every
switch, which the spec explicitly rules out (aim should stay
continuous across a switch, matching the existing "no reconnect"
guarantee for switching).

**The manual `/cursor/move` route keeps the unwrapped backend.**
`app.state.cursor_backend` (used by the route) stays the raw backend;
only the copy handed to `MarkerSourceController` gets wrapped. Two
references to logically different backends, same underlying device —
consistent with the existing fact that `click()` already depends on
`move_absolute` having been called by whoever last moved the cursor, be
that a solved frame or a manual request.

**One-euro filter, timestamped by a monotonic clock at each call, not by
frame count.** The filter needs a `dt` between updates; using real
elapsed time (rather than assuming a fixed rate) matches the existing
frame pipeline, which already tolerates uneven Wi-Fi delivery and
dropped frames. A monotonic clock (rather than wall-clock time) avoids
`dt` going backward or spiking across a system clock adjustment, at no
extra cost. Because `AimPipeline` only calls `move_absolute` for a
*solved* frame, a dropout period (no markers, insufficient
correspondences, solve failure) naturally never touches the filter; the
next solved frame after a gap arrives with a larger `dt`, which the
one-euro filter's own speed-adaptive cutoff already treats as fast
motion — exactly the "don't crawl back" behavior wanted, with no extra
gap-detection logic needed.

**Trigger behavior needs no change.** `click()` already fires at
whatever `move_absolute` last set — once that call is the filtered one,
the click follows automatically. This is called out as a requirement in
the new spec because the change makes it meaningful, not because the
code changes.

## Risks / Trade-offs

- **Fixed tuning constants may not suit every camera/lighting setup.**
  → Accepted for this change (Non-Goal); defaults are picked for a
  visibly-jitter-prone setup and can be revisited as a follow-up if
  real use shows they're wrong for a different camera or distance.
- **A decorator around `CursorBackend` is one more layer between
  `AimPipeline` and the OS cursor**, which is one more place a bug in
  positioning could hide. → Mitigated by keeping the decorator small
  (position only, `click` untouched) and testing it in isolation
  against a `FakeCursorBackend`, the same way the rest of the backend
  layer is already tested.
- **A first update after process start (or after a very long dropout)
  has no prior sample to compute a meaningful `dt` from.** → The
  filter's first call initializes its state from that sample and emits
  it unfiltered, the same way a one-euro filter ordinarily bootstraps —
  no special-casing needed.
