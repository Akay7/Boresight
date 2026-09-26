# marker-detection Specification

## Purpose
Finds fiducial markers in a camera frame and reports each one's id and
image-plane corner positions, accurately enough that the homography
solved from them does not turn corner noise into aim noise.

## Requirements

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

### Requirement: A session can detect faster by tracking its markers
The system SHALL provide a per-session detector that remembers which
markers the session's previous frame found and, while every one of
them was large enough to be found reliably at reduced resolution,
searches a downscaled copy of the frame and then refines each corner
against the full-resolution frame. It SHALL return the same kind of
result as full-frame detection: each marker's id and its four corners
in the pixels of the original, full-resolution frame. On a frame where
it searches at reduced resolution, its corners SHALL NOT deviate from
the corners full-frame detection gives for the same marker in the same
frame by more than 0.1px, and SHALL stay within the sub-pixel bound
full-frame detection meets against ground truth.

#### Scenario: Reduced-resolution corners match the full pass
- **WHEN** the phone-resolution video fixture is detected frame by frame
  through a per-session detector
- **THEN** it finds the same markers on every frame as full-frame
  detection, most frames are searched at reduced resolution, and every
  corner lies within 0.1px of full-frame detection's corner for that
  marker

#### Scenario: Reduced-resolution corners meet the ground-truth bound
- **WHEN** the checked-in synthetic photo is detected repeatedly through
  a per-session detector, so that later frames are searched at reduced
  resolution
- **THEN** every corner of those frames lies within 0.8px of its
  ground-truth position

#### Scenario: Small markers are never searched at reduced resolution
- **WHEN** the ESP32-CAM video fixture, whose markers are about 25px
  across, is detected through a per-session detector
- **THEN** every frame is searched at full resolution and the result is
  identical to full-frame detection

### Requirement: Tracked detection falls back to a full-frame search
When a reduced-resolution search does not find every marker the
session's previous frame found, or finds a marker too small to trust
at that resolution, the per-session detector SHALL search the full
frame at full resolution for that same frame and return that result,
so a reduced-resolution miss costs time and never a detection. It
SHALL search the full frame whenever the previous frame found no
markers.

#### Scenario: A lost marker is searched for in the same frame
- **WHEN** a marker the previous frame found is not found by the
  reduced-resolution search of the current frame
- **THEN** the detector returns, for the current frame, exactly what
  full-frame detection returns for it

#### Scenario: Nothing tracked means a full search
- **WHEN** the session's previous frame found no markers, or the session
  has just started
- **THEN** the current frame is searched in full

### Requirement: New markers are found within a bounded number of frames
The per-session detector SHALL search the full frame at least once
every 10 frames regardless of what it is tracking, so that a marker
that comes into view is detected within 10 frames of becoming
detectable by full-frame detection, even if it is too small for the
reduced-resolution search to find.

#### Scenario: A marker that appears is found within the bound
- **WHEN** a session is tracking a set of markers and another marker,
  hidden until then, becomes visible and stays visible
- **THEN** the detector reports it no later than the 10th frame after
  it appears

### Requirement: Tracking state belongs to one session
Each session SHALL detect through a tracking state of its own, fed only
by that session's frames, so what one session's camera saw never
changes where or how another session's frames are searched, and
concurrent sessions each get the result they would get alone.

#### Scenario: Interleaved sessions detect as if alone
- **WHEN** frames from two sessions showing different sequences are
  detected alternately, each through its own session's detector
- **THEN** each session's results are identical to detecting its
  sequence alone

### Requirement: Tracked detection can be turned off
The server SHALL offer a startup option that disables tracked
detection, so that every frame of every session is searched in full at
full resolution exactly as full-frame detection does.

#### Scenario: Full-frame detection on request
- **WHEN** the server is started with tracked detection disabled
- **THEN** every session's frames are detected by full-frame detection
