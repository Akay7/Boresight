## MODIFIED Requirements

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
