## Purpose

Smooths the aim-derived cursor position over time so that ordinary
per-frame detection noise does not show up as visible jitter while the
player holds aim, without adding perceptible lag when the aim point
moves quickly to a new target.

## ADDED Requirements

### Requirement: Aim-derived cursor movement is smoothed against per-frame noise
The system SHALL smooth the normalized cursor position derived from
solved frames before it reaches the OS cursor, so that small
frame-to-frame variation in an otherwise steady aim point is
attenuated rather than passed straight through.

#### Scenario: A steady aim point produces a steady cursor
- **WHEN** consecutive solved frames report aim points that vary only by
  small, noise-scale amounts around one location
- **THEN** the emitted cursor position varies by less than the raw aim
  point does, staying visibly steadier than the unsmoothed input

### Requirement: Smoothing does not add perceptible lag to fast movement
The system SHALL respond quickly to a large, sustained change in the
aim point, rather than applying the same degree of smoothing regardless
of how fast the aim point is moving.

#### Scenario: A fast swing to a new target tracks closely
- **WHEN** consecutive solved frames report the aim point moving quickly
  and consistently toward a new location, well beyond noise-scale
  variation
- **THEN** the emitted cursor position tracks the new location closely,
  with substantially less delay than the smoothing applied to a steady
  aim point

### Requirement: Smoothing uses real elapsed time, not assumed frame timing
The system SHALL base smoothing on the actual time elapsed between
solved frames rather than assuming a fixed interval, and SHALL treat a
gap since the last solved frame as ordinary elapsed time rather than
something to catch up toward smoothly.

#### Scenario: Irregular frame timing is smoothed consistently
- **WHEN** solved frames arrive with uneven spacing between them
- **THEN** the degree of smoothing applied reflects the actual time
  elapsed between the frames used, not a fixed assumed frame rate

#### Scenario: Resuming after a dropout does not overshoot or crawl back
- **WHEN** a period with no solved frame is followed by a new solved
  frame at a different location
- **THEN** the emitted cursor position responds to the new frame as a
  fresh update, without a delayed sweep through positions reported
  before the gap

### Requirement: Smoothing carries over across a marker-source switch
The system SHALL preserve its smoothing state across a change of marker
source, so that switching between printed and on-screen markers while
streaming does not reset or discontinue the smoothing applied to the
emitted cursor position.

#### Scenario: Switching marker source mid-stream does not jolt the cursor
- **WHEN** the marker source is switched while frames are being solved
  and the aim point does not itself change
- **THEN** the emitted cursor position continues smoothly through the
  switch, with no jump or reset attributable to the switch itself

### Requirement: Manually requested cursor positions are exact
The system SHALL NOT apply aim smoothing to a cursor position that was
explicitly requested rather than derived from a solved frame; such a
request SHALL move the cursor to exactly the requested position.

#### Scenario: An explicit move request is not smoothed
- **WHEN** a client explicitly requests the cursor move to a specific
  normalized position, outside of the aim pipeline
- **THEN** the cursor moves to exactly that position, unaffected by any
  smoothing state built up from aim-derived movement

### Requirement: A trigger press fires at the smoothed position
The system SHALL fire the trigger at the same position the smoothed
cursor is currently displaying, so that what the player sees at the
moment of the shot is where it lands.

#### Scenario: A press lands where the visible cursor is
- **WHEN** the trigger is pressed while aim smoothing has moved the
  cursor to a position that differs from the latest raw solved aim
  point
- **THEN** the resulting click fires at the smoothed position the
  cursor was last moved to, not the unsmoothed aim point
