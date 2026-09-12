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
The pipeline SHALL clamp normalized coordinates into `[margin, 1.0 -
margin]` before emitting them, for a small fixed margin, rather than
into the full `[0.0, 1.0]` range — both when the aim point is a
physical position that legitimately falls outside the active panel
(the cursor backend accepts only the clamped range) and when a
genuine, on-panel solve lands at or very near the panel's physical
edge. The cursor device the pipeline emits to is classified as a
touchscreen so it positions directly rather than through relative-
motion acceleration; several desktop environments bind an action (e.g.
show-desktop, edge-swipe overview) to a pointer reaching the literal
screen edge, which a value of exactly `0.0` or `1.0` would trigger
indistinguishably from a real touch. The pipeline SHALL report both
the unclamped millimetre aim point and whether clamping occurred, so
an off-panel aim is observable rather than silently indistinguishable
from an aim at the margin.

#### Scenario: An off-panel aim point is clamped, not rejected
- **WHEN** the solver returns an aim point beyond the panel edge
- **THEN** the emitted normalized coordinates lie within `[margin, 1.0
  - margin]`, not at the literal `0.0`/`1.0` edge
- **AND** the result reports the unclamped millimetre aim point and
  indicates that the emitted position was clamped

#### Scenario: A near-edge on-panel aim point never reaches the literal edge
- **WHEN** the solver returns an aim point on the panel but within the
  margin of its physical edge
- **THEN** the emitted normalized coordinates are still bounded away
  from the literal `0.0`/`1.0` edge by the margin

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

### Requirement: The per-frame operation can report its geometry on request
The per-frame operation SHALL accept a request for debug output and,
when asked, SHALL return alongside its normal result the geometry that
produced it, expressed in the coordinates of the frame it was given:
the size of that frame in pixels, and every detected marker with its
ID, its four corners in image pixels, and whether the layout maps it.
Debug output SHALL be off by default, SHALL be requested per call
rather than held on the pipeline, and SHALL NOT change the outcome,
the emitted position, or anything else the operation returns. The
pipeline instance is shared between concurrent sessions, so a request
from one caller must not alter what another caller's frames compute.

#### Scenario: Debug output is absent unless requested
- **WHEN** a frame is processed without requesting debug output
- **THEN** the result carries no debug geometry, and its outcome,
  counts and emitted position are identical to what the same frame
  produces when debug output is requested

#### Scenario: Detections are reported with their image coordinates
- **WHEN** a frame containing detectable markers is processed with
  debug output requested
- **THEN** the result carries the frame's pixel size and one entry per
  detected marker, each giving that marker's ID, its four corners in
  image pixels, and whether the marker map declares it

#### Scenario: Markers the layout ignores are reported as ignored, not omitted
- **WHEN** a frame containing a detected marker absent from the layout
  is processed with debug output requested
- **THEN** that marker appears in the debug geometry marked as not
  mapped, so a tag that is being seen and skipped is distinguishable
  from one that is not being seen at all

### Requirement: Debug geometry places the solve back in image space
When a frame solves and debug output is requested, the operation SHALL
additionally report, in image pixels: the four corners of the
configured screen rectangle projected through the solved homography,
and the position actually emitted to the cursor backend carried back
through that same homography. The emitted position SHALL be the one
that is reported — normalized against the screen size and clamped as
emitted — rather than the unclamped solved aim point, because pushing
the solved aim point back through its own homography returns the image
centre by construction and can never disagree with it. The operation
SHALL also report the reprojection error of the fit.

#### Scenario: The screen rectangle is projected into the image
- **WHEN** a frame solves with debug output requested
- **THEN** the debug geometry carries four image-pixel points
  corresponding to the corners of the configured screen size in
  millimetres, transformed by the homography that produced the aim
  point

#### Scenario: The emitted position is carried back into the image
- **WHEN** a frame solves with debug output requested and the emitted
  position was clamped to the edge margin
- **THEN** the reported image-pixel position of the cursor corresponds
  to the clamped, emitted position rather than to the unclamped aim
  point, and therefore does not coincide with the image centre

#### Scenario: An unsolved frame reports detections without a projection
- **WHEN** a frame is processed with debug output requested and does
  not solve
- **THEN** the debug geometry still carries the image size and any
  detections, and carries no screen rectangle, no cursor position and
  no reprojection error, rather than carrying values from an earlier
  frame

#### Scenario: A frame with no detections is distinguishable from debug being off
- **WHEN** a frame containing no detectable markers is processed with
  debug output requested
- **THEN** the result carries debug geometry with an empty list of
  markers, rather than carrying no debug geometry at all
