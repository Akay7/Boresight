## Purpose

Decides which of several connected clients drives the one OS cursor, so
that simultaneous streams never fight over it or get blended together,
and lets control pass cleanly from one shooter to the next.

## ADDED Requirements

### Requirement: One session drives the cursor at a time
At any moment at most one frame session SHALL own the cursor. Aim
derived from the owner's frames, including a held position during a
brief dropout and the aim a trigger fires at, SHALL move the cursor;
aim derived from any other session's frames SHALL NOT. Frames from a
session that does not own the cursor SHALL still be decoded, solved and
reported to that session exactly as they would be otherwise.

#### Scenario: A second phone does not move the cursor
- **WHEN** session A owns the cursor and keeps producing aim, and
  session B streams frames that solve to a different aim point
- **THEN** the cursor follows only A's aim, and B still receives its
  own per-frame reports with its own solved positions

### Requirement: Pressing the trigger takes the cursor
A session that presses the trigger — a plain trigger or a `down` that
presses — SHALL become the owner of the cursor before the press is
carried out, even if another session owned it.

#### Scenario: The most recent shooter takes over
- **WHEN** session A owns the cursor and session B presses the trigger
- **THEN** B owns the cursor, the press is carried out for B, and from
  then on only B's aim moves the cursor

### Requirement: An unowned cursor goes to the first session that aims
When no session owns the cursor, the first session to produce an aim
point SHALL take it. The cursor SHALL become unowned when its owner
disconnects, or when its owner has produced no aim for 1 second.

#### Scenario: The first session to aim takes a free cursor
- **WHEN** nobody owns the cursor and session A's frame solves
- **THEN** A owns the cursor and its aim moves it

#### Scenario: Ownership passes when the owner disconnects
- **WHEN** the owning session disconnects while another session is
  aiming
- **THEN** the other session's next aim point takes the cursor

#### Scenario: Ownership passes when the owner stops aiming
- **WHEN** the owning session produces no aim for 1 second (it lost
  the markers, stalled, or stopped streaming) while another session is
  aiming
- **THEN** the other session's next aim point takes the cursor

### Requirement: Each session is smoothed and held on its own
Each session SHALL have its own aim smoothing and its own brief-dropout
hold, fed only by its own frames. A change of owner SHALL NOT blend one
session's aim into another's. Within a session, smoothing SHALL carry
across a change of marker source, and a held position SHALL NOT carry
across it.

#### Scenario: A handover does not blend two streams
- **WHEN** ownership passes from session A to session B
- **THEN** the cursor moves to B's own smoothed aim, computed from B's
  frames alone, with no contribution from A's

### Requirement: Each session is told whether it drives the cursor
Every stats message SHALL carry a `cursor` field: `yours` if the session
owns the cursor, `other` if another session does, and `free` if nobody
does.

#### Scenario: Two sessions see who has the cursor
- **WHEN** session A owns the cursor and both A and B receive stats
- **THEN** A's stats say `yours` and B's say `other`
