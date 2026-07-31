# aim-pipeline Specification

## Purpose
TBD - created by archiving change add-aim-pipeline. Update Purpose after archive.
## Requirements
### Requirement: A single operation turns a frame into a cursor position
The system SHALL provide one per-frame operation that takes a captured
frame and, using a marker map, runs marker detection, pairs each detected
marker's image-plane corners with that marker's screen-plane corners,
solves for the aim point, converts it to normalized screen coordinates,
and emits it to a cursor backend. The operation SHALL be stateless and
synchronous: it retains nothing between frames, and calling it twice on
the same frame produces the same result and the same emission.

#### Scenario: A solvable frame moves the cursor
- **WHEN** the operation is given a frame in which enough mapped markers
  are detected to solve
- **THEN** it emits exactly one absolute move to the cursor backend, at
  the normalized coordinates corresponding to the solved aim point
- **AND** it returns a result carrying the aim point in millimetres, the
  normalized coordinates, the number of markers detected, and the
  solve's conditioning

#### Scenario: Repeated calls on one frame are identical
- **WHEN** the operation is called twice on the same frame
- **THEN** both calls return equal results and each emits its own move,
  with no dependence on the earlier call

### Requirement: Aim point is normalized against the configured screen size
The pipeline SHALL convert the solver's millimetre aim point to
normalized coordinates by dividing by the screen dimensions declared in
the marker map, so that the top-left corner of the active display maps to
`(0.0, 0.0)` and its bottom-right corner to `(1.0, 1.0)`. It SHALL NOT
infer the screen size from the frame, the marker positions, or the
cursor backend.

#### Scenario: Screen centre normalizes to the midpoint
- **WHEN** the solver returns an aim point at the centre of the declared
  screen area
- **THEN** the emitted normalized coordinates are `(0.5, 0.5)`

### Requirement: Aim points beyond the panel edge are clamped before emission
The pipeline SHALL clamp normalized coordinates into `[0.0, 1.0]` before
emitting them, because the aim point is a physical position that may
legitimately fall outside the active panel while the cursor backend
accepts only that range. It SHALL report both the
unclamped millimetre aim point and the fact that clamping occurred, so an
off-panel aim is observable rather than silently indistinguishable from
an aim at the very edge.

#### Scenario: An off-panel aim point is clamped, not rejected
- **WHEN** the solver returns an aim point beyond the panel edge
- **THEN** the emitted normalized coordinates lie within `[0.0, 1.0]`
- **AND** the result reports the unclamped millimetre aim point and
  indicates that the emitted position was clamped

### Requirement: Frames that cannot be solved emit nothing
The pipeline SHALL NOT emit a cursor move for a frame it cannot solve —
whether because no markers were detected, because too few mapped markers
were detected to fit a homography, or because the solver rejected the
correspondences — and SHALL NOT raise out of the per-frame operation for
these cases. It SHALL instead return a result identifying the frame as
unsolved and naming the reason. Holding the last good position and
decaying it is deliberately out of scope here and belongs to the
filtering stage; this requirement establishes only that an unsolvable
frame never moves the cursor to a fabricated position.

#### Scenario: A frame with no detectable markers is skipped
- **WHEN** the operation is given a frame in which the detector finds no
  markers
- **THEN** the cursor backend receives no call
- **AND** the result identifies the frame as unsolved with no markers
  detected

#### Scenario: Too few correspondences to solve is skipped
- **WHEN** the operation is given a frame yielding fewer correspondences
  than a homography requires
- **THEN** the cursor backend receives no call, and the result identifies
  the frame as unsolved because there were insufficient correspondences,
  rather than the solver's error propagating to the caller

### Requirement: Detected markers absent from the map are ignored
The pipeline SHALL contribute correspondences only for detected markers
the marker map declares, and SHALL ignore any other detected ID rather
than failing the frame. A frame containing both mapped and unmapped
markers SHALL be solved from the mapped ones alone.

#### Scenario: An unmapped marker does not fail the frame
- **WHEN** a frame yields detections for several mapped markers plus one
  ID the layout does not declare
- **THEN** the frame is solved from the mapped markers only, and the
  unmapped detection contributes no correspondences and causes no error
- **AND** the result reports how many detections were ignored

### Requirement: Poorly conditioned solves are emitted and flagged, not suppressed
The pipeline SHALL emit the aim point of a solve the solver flags as
poorly conditioned, and SHALL surface that flag in its result rather than
withholding the move. Suppression is incorrect as a policy: a flagged
solve indicates the aim point was extrapolated beyond the visible
markers, which bounds nothing about its accuracy — close-range frames
with a single large marker in view have been measured accurate to a few
millimetres while flagged. Deciding to discount a flagged aim point is
the filtering stage's responsibility, and depends on state this stateless
operation does not have.

#### Scenario: A flagged solve still moves the cursor
- **WHEN** the operation solves a frame whose aim point falls outside the
  convex hull of its correspondences
- **THEN** the cursor backend still receives the move
- **AND** the result reports the solve as poorly conditioned, along with
  the signed distance from the correspondence hull

### Requirement: Recorded frame sequences replay through the real pipeline
The system SHALL provide an entry point that replays a checked-in frame
sequence through the same per-frame operation used in production,
against a selectable cursor backend, so the detect-solve-inject path can
be exercised and demonstrated end to end without a camera, a phone, or a
network.

#### Scenario: A rendered fixture sequence replays end to end
- **WHEN** a rendered frame sequence is replayed through the pipeline
  against a recording backend
- **THEN** the sequence of emitted normalized positions corresponds,
  within a documented tolerance, to the ground-truth aim points recorded
  in that sequence's manifest

#### Scenario: A sequence containing unsolvable frames replays without failing
- **WHEN** a replayed sequence contains frames captured too close to the
  display for any marker to be in view
- **THEN** the replay completes, emitting moves only for the solvable
  frames and reporting the unsolved ones
