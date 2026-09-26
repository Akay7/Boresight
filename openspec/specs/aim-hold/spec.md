# aim-hold Specification

## Purpose
Keeps the emitted cursor position alive on the cursor backend through a
brief run of frames that fail to solve, so a short detection gap does
not read to the player as the cursor going idle or disappearing, and
lets that hold lapse once the gap runs longer than an ordinary dropout.

## Requirements

### Requirement: A brief dropout re-sends the last solved position
The system SHALL re-send a session's most recently solved cursor
position toward the cursor when that session's frame does not solve,
provided that session saw a solved frame within a fixed hold window
before it. The hold SHALL be the session's own: it SHALL be fed only by
that session's frames, and a re-sent position SHALL reach the cursor
only while that session drives it (see cursor-ownership).

#### Scenario: A short run of unsolved frames keeps the cursor active
- **WHEN** one or a few consecutive frames of the session driving the
  cursor fail to solve, following a frame of that session that did
  solve within the hold window
- **THEN** the cursor backend receives the same position again for each
  unsolved frame in that run

#### Scenario: One session's dropout never re-sends another's position
- **WHEN** session A has solved frames, and session B, which has solved
  none, sends a frame that does not solve
- **THEN** nothing is re-sent on B's behalf, and A's position is not
  re-sent because of B's frame

### Requirement: Holding does not move or perturb the cursor
The system SHALL re-send exactly the position last solved, unchanged, so
holding has no visible effect on where the cursor is.

#### Scenario: A held position matches the last solved one exactly
- **WHEN** the system re-sends a position because the current frame did
  not solve
- **THEN** the position sent is identical to the last position emitted
  from a solved frame, not a new or extrapolated one

### Requirement: Holding lapses after a fixed window
The system SHALL stop re-sending a held position once the time since the
last solved frame exceeds the hold window, allowing the cursor to go
idle rather than holding indefinitely on a position that may no longer
reflect where the player is aiming. The hold window SHALL default to
0.75 seconds and SHALL be a runtime setting (see runtime-settings): a
change SHALL apply to every session from its next frame, measured from
that session's last solved frame, and a window of zero SHALL disable
holding.

#### Scenario: A long dropout is not held forever
- **WHEN** no frame solves for longer than the hold window
- **THEN** the system stops re-sending the last position, and the cursor
  backend receives nothing further until a new frame solves

#### Scenario: A shorter window applies to a session already holding
- **WHEN** a session's last solve was 0.5 seconds ago and the hold
  window is changed from 0.75 to 0.25 seconds
- **THEN** that session's next unsolved frame re-sends nothing

### Requirement: Holding does not change what is reported over the wire
The system SHALL report each frame's real outcome to the client exactly
as it would without holding; holding affects only what reaches the
cursor backend.

#### Scenario: A held frame is still reported as unsolved
- **WHEN** a frame does not solve and its position is held on the
  cursor backend
- **THEN** the outcome and debug information reported to the client for
  that frame are exactly what a non-solved frame without holding would
  report, with no cursor position implied

### Requirement: A new solve replaces the held position immediately
The system SHALL treat a newly solved frame exactly as it would without
holding, whether or not a hold was in effect when it arrived.

#### Scenario: Detection recovers mid-hold
- **WHEN** a frame solves again while a previous position is still being
  held
- **THEN** the newly solved position is emitted as usual, and holding
  resets to track this new position and its own time going forward
