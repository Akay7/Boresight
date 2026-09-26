## ADDED Requirements

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
