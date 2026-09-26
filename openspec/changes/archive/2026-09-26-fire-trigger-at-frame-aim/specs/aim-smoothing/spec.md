## REMOVED Requirements

### Requirement: A trigger press fires at the smoothed position
**Reason**: The smoothed cursor trails a fast swing, so a shot fired
where it is lands behind where the player was aiming. A trigger that
names its frame now fires at that frame's unsmoothed aim point (see
trigger-emission, "A trigger fires at the aim point of the frame it
names").
**Migration**: Clients send `frame_ms` with a click or `down` to fire at
the frame's aim. A trigger without `frame_ms` still fires where the
smoothed cursor is, as stated by "A shot bypasses smoothing only when it
names its frame".

## ADDED Requirements

### Requirement: A shot bypasses smoothing only when it names its frame
A trigger that names no frame SHALL fire at the position the smoothed
cursor is currently displaying. A trigger that names a frame SHALL fire
at that frame's unsmoothed aim point instead, as trigger-emission
describes, and the move it makes to get there SHALL NOT feed the
smoothing: the next solved frame is smoothed from the filter's own
state, as if the shot had not happened.

#### Scenario: A legacy press lands where the visible cursor is
- **WHEN** a trigger without `frame_ms` is pressed while smoothing has
  moved the cursor to a position that differs from the latest raw
  solved aim point
- **THEN** the click fires at the smoothed position the cursor was last
  moved to

#### Scenario: A named shot leaves the filter alone
- **WHEN** a trigger naming a frame moves the cursor to that frame's
  unsmoothed aim point and presses there, and another frame then solves
- **THEN** that frame's emitted position is the one the filter would
  have produced had the shot not been fired
