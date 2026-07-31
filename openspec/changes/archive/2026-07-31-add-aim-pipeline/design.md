## Context

`detect.py`, `solve.py` and `inject.py` each work and each is tested, but
no code joins them. The join needs one missing piece — a marker map — and
one missing composition — a per-frame operation.

The marker map is not speculative work: the reference layout already
exists, hardcoded as `MARKER_LAYOUT_MM` in
`tests/generate_synthetic_video_fixture.py`, copied into every fixture
manifest, and re-derived per test by `_marker_corners_mm()` in
`tests/test_solve_video_e2e.py` and `tests/test_solve_partial_markers.py`.
This change gives that data a home in `config/markers.toml`, in the format
README already documents.

Two existing decisions constrain the composition:

- `solve.py` is deliberately policy-free. It returns a best-effort aim
  point whenever it has four correspondences and never refuses on
  conditioning grounds, because "what to do about a low-confidence aim
  point is the consumer's call" (`homography-solve` spec). This change
  creates that consumer, so the policy has to be decided here.
- `inject.py`'s `CursorBackend` protocol takes normalized `[0.0, 1.0]`
  coordinates. The solver produces millimetres, which can legitimately
  fall outside the panel. Something has to bridge that, and the bridge
  needs the screen size — which only the marker map knows.

## Goals / Non-Goals

**Goals:**

- A frame goes in, the OS cursor moves. One function, no orchestration
  layer.
- The reference layout lives in one place, and drift between that place
  and the rendered fixtures is a test failure.
- Every existing fixture becomes end-to-end coverage of the whole
  software path, at zero fixture-regeneration cost.
- Every branch `solve.py` pushed to its consumer has an explicit,
  specified, tested answer.

**Non-Goals:**

- Filtering. No 1-euro, no smoothing, no hold-last-good-and-decay. The
  pipeline is where `filter.py` will slot in; it is not `filter.py`.
- Detection improvements. No `cornerSubPix`, no `undistortPoints` —
  the latter is blocked on calibration anyway.
- Server, WebSocket, phone client, video decode, threading, async, or
  any real capture source.
- `solvePnP` for sparse markers. Also blocked on calibration.
- Performance work. The replay path exists to demonstrate correctness,
  not to establish a latency number; README is explicit that real
  latency has to be measured against real hardware and a real network
  hop.

## Decisions

### `MarkerMap` is a loaded, validated object, not a dict

`load_marker_map(path) -> MarkerMap` parses with `tomllib` (standard
library — no dependency added) and validates eagerly. `MarkerMap` holds
`screen_size_mm` and the markers, and exposes `corners_mm(marker_id)`
returning the four screen-mm corners clockwise from top-left, or `None`
for an unknown ID.

*Why not return a plain dict:* the map has invariants (unique IDs,
positive sizes, a screen size) and one derived operation (position +
size → four ordered corners) that would otherwise be re-implemented by
each caller. It already has been, three times, in the tests.

*Why `size_mm` per marker rather than one layout-wide constant:* README
anticipates "a second inner ring for very close play on large displays",
which would use smaller tags. Per-marker size costs nothing now and
avoids a format break later. The reference layout happens to use 80mm
throughout.

*Why `None` rather than raising on unknown IDs:* the pipeline's correct
response to an unmapped detection is to skip it, and a stray ArUco code
in the room is a real possibility. Making absence a return value rather
than an exception keeps that path from reading like error handling.
Note this is a genuine bug today: `test_solve_video_e2e.py` does
`layout_mm[marker.marker_id]`, which would raise on any unexpected ID.

### The pipeline is a function on a small context object, not a class hierarchy

`AimPipeline(marker_map, backend)` with `process_frame(frame) ->
FrameResult`. It holds only its collaborators; it holds no per-frame
state. `FrameResult` is a dataclass carrying the outcome, the millimetre
aim point, the normalized emitted position, marker counts, and the
solve's conditioning.

*Why an object at all, rather than a free function taking every
collaborator:* `process_frame` is called once per frame in a loop, and
the map and backend are fixed for the lifetime of a session. Binding
them once keeps the per-frame call site honest about what actually
varies.

*Why not make it a generator or async:* nothing here is I/O-bound in the
current slice, and the eventual caller (a WebSocket handler) will want
to drive it frame by frame from its own loop rather than hand it a
stream.

### Grayscale conversion happens inside the pipeline

README's pipeline starts with grayscale, and a camera hands over colour.
`process_frame` accepts either and converts if the frame has three
channels, so callers do not each re-implement the same `cvtColor` call —
as both existing e2e tests currently do.

### Unsolvable frames are a returned outcome, not an exception

`FrameResult.outcome` is an enum: `SOLVED`, `NO_MARKERS`,
`INSUFFICIENT_CORRESPONDENCES`, `SOLVE_FAILED`. The pipeline catches
`InsufficientCorrespondencesError` and the solver's degenerate-homography
`ValueError` and converts them to outcomes.

*Why:* dropout is the expected steady state, not an error. README calls
it out directly — "Detection will fail for a few frames mid-swing" — and
the close-range fixture contains frames with literally zero markers in
view. A caller that has to wrap every frame in `try/except` to handle the
normal case has the wrong interface. Exceptions stay for programmer
errors (a malformed config file), not for a swing past the edge of the
marker layout.

*Alternative rejected:* emitting the last good position on an unsolvable
frame. That is decay policy, it needs state, and doing it here would
quietly pre-empt `filter.py`'s design. The pipeline emits nothing, which
leaves the cursor where it was — the same visible behaviour, without
inventing a position or claiming a confidence.

### Flagged (poorly conditioned) solves are emitted anyway

*Why not suppress:* the measurement in README's "Marker visibility and
accuracy" section shows flagged does not mean wrong. Close-range frames
with one or two visible markers were flagged yet accurate to 1.1–6.3mm,
because a nearer marker occupies more pixels and localises better.
Suppressing flagged solves would blank the cursor in exactly the
close-range case the midpoint marker ring exists to serve.

*Why not threshold on `aim_point_hull_distance_mm`:* any threshold is a
tuning parameter, and tuning it needs the temporal context the filter
will have and this operation does not. The flag is propagated so the
filter can weight on it later.

### Clamping is done at the emission boundary and reported

Normalized coordinates are clamped into `[0.0, 1.0]` immediately before
`move_absolute`; `FrameResult` keeps the unclamped millimetre aim point
and a `clamped: bool`.

*Why clamp rather than skip:* aiming slightly past the panel edge is
ordinary use, and the cursor should sit at the edge, not freeze. *Why
report it:* clamped output is otherwise indistinguishable from an aim at
the exact edge, and "the cursor is stuck in a corner" is a symptom worth
being able to diagnose.

### `config/markers.toml` is checked against the fixture manifests

A test asserts the shipped layout and each fixture manifest describe the
same screen size, IDs, positions and sizes.

*Why:* the fixtures are rendered from constants in the generator, and the
config is now a separate file. Without this test they can drift, and the
symptom would be a mysterious accuracy regression rather than an obvious
config mismatch. This also documents that the shipped config is not
arbitrary — it is the layout the whole test suite's accuracy numbers were
measured against.

*Note:* this makes `config/markers.toml` the reference layout, not a
user's layout. A real installation will have different numbers; the
consistency test is scoped to the shipped file only.

### Replay entry point: `python -m boresight.pipeline <frames-dir>`

Reads a manifest, replays the frames through `process_frame`, and by
default emits to the real uinput backend so the cursor visibly moves.
`--dry-run` swaps in a recording backend and prints the track.

*Why include it:* it is the difference between "the modules compose in a
test" and "you can watch it work". It also gives the e2e tests and a
human the same code path.

### Tests reuse the fixtures; no fixture is regenerated

The two rendered fixtures are Git-LFS-tracked binary assets whose
determinism was established at some cost. This change must not alter a
single fixture byte, and the new e2e tests read them exactly as the
existing solver tests do.

The existing solver tests keep their own correspondence assembly rather
than being rewritten on top of `MarkerMap`. They test `solve.py` in
isolation, and routing them through the new code would make a
`marker_map.py` bug look like a solver regression.

## Risks / Trade-offs

**The pipeline duplicates correspondence assembly that already exists in
tests** → Accepted, and deliberate per the previous point. The
duplication is one small function; conflating solver tests with pipeline
tests would cost more than it saves.

**`config/markers.toml` is a reference layout being shipped in a
location that implies it is *the* config** → Mitigated by the consistency
test and by documenting it as the reference layout in README. Real
installations will need the marker-map calibration tool, which is a
separate milestone.

**Clamping hides a class of bug**: a wildly wrong aim point (the 2m error
a single-marker extrapolation produced) clamps to a screen corner and
looks like a plausible cursor position → Mitigated by reporting
`clamped` and the conditioning flag on every frame, and by asserting in
tests that clamping is reported rather than silent. The real fix is
`solvePnP`, blocked on calibration.

**Emitting flagged solves means the cursor can jump 2m-equivalent on a
bad frame** → Accepted for this change, and stated plainly: without
temporal state there is no principled way to reject it, and rejecting on
conditioning alone would break the close-range case. This is the
strongest argument for `filter.py` being the next change after this one.

**No real capture source means the pipeline's interface is designed
against fixtures** → Mitigated by keeping `process_frame` to a single
numpy array in and a result out, which is what any capture source will
hand over. The parts most likely to need rework — frame decode, timing,
backpressure — are all deliberately outside it.
