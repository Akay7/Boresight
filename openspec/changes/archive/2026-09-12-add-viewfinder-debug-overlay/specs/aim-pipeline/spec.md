## ADDED Requirements

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
