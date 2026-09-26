## Purpose

Finds fiducial markers in a camera frame and reports each one's id and
image-plane corner positions, accurately enough that the homography
solved from them does not turn corner noise into aim noise.

## ADDED Requirements

### Requirement: Marker corners are localised to sub-pixel accuracy
The detector SHALL refine each detected marker's corners to sub-pixel
positions on the marker's actual outer edge before returning them,
rather than returning the integer-precision vertices of the detected
contour. The refinement SHALL be scaled to the size at which the marker
appears in the frame, so that it improves corner accuracy both for
markers tens of pixels across (a low-resolution camera) and for markers
hundreds of pixels across, without pulling a corner toward the marker's
interior data bits.

#### Scenario: Corners of a known warp land within a sub-pixel bound
- **WHEN** the detector is run on the checked-in synthetic photo, whose
  marker corners are known exactly from its ground-truth homography
- **THEN** every detected corner lies within 0.8px of its ground-truth
  position

#### Scenario: Refinement does not cost detections
- **WHEN** the detector is run over every frame of each checked-in
  fixture
- **THEN** it finds the same markers it would find without corner
  refinement, and the close-range fixture's per-frame marker counts
  still match the counts recorded when it was generated

#### Scenario: Refinement reduces frame-to-frame aim jitter
- **WHEN** the full-visibility video fixtures are detected and solved
  frame by frame
- **THEN** the frame-to-frame change in the solved aim point tracks the
  ground-truth change to within 0.5mm on the phone-resolution fixture
  and 1.0mm on the ESP32-CAM fixture

### Requirement: Detection is safe to run concurrently
The detector SHALL return, for a given frame, exactly the same markers
and corners whether it is called from one thread or from several
threads at once, and SHALL NOT share mutable detection state between
calls running concurrently on different threads. Detection state that
is expensive to build SHALL be reused across frames on the same thread
rather than rebuilt per frame.

#### Scenario: Concurrent sessions get the same answer as one
- **WHEN** the frames of a fixture are detected concurrently from
  several threads, as the server does for simultaneous streaming
  sessions
- **THEN** every frame's detected markers and corners are identical to
  detecting that frame alone on a single thread

#### Scenario: Per-thread reuse
- **WHEN** detection runs on the same thread for successive frames
- **THEN** it reuses the same detector rather than constructing a new
  one per frame, and a different thread uses a detector of its own
