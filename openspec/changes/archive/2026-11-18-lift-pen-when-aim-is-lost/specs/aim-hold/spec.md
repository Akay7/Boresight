## MODIFIED Requirements

### Requirement: Holding lapses after a fixed window
The system SHALL stop re-sending a held position once the time since the
last solved frame exceeds the hold window, and SHALL then tell the
cursor that nothing is aiming, on each unsolved frame until a frame
solves again, rather than holding indefinitely on a position that may
no longer reflect where the player is aiming. With holding disabled, an
unsolved frame SHALL tell the cursor the same at once. The hold window
SHALL default to 0.75 seconds and SHALL be a runtime setting (see
runtime-settings): a change SHALL apply to every session from its next
frame, measured from that session's last solved frame, and a window of
zero SHALL disable holding.

#### Scenario: A long dropout is not held forever
- **WHEN** no frame solves for longer than the hold window
- **THEN** the system stops re-sending the last position, and each
  further unsolved frame tells the cursor backend that nothing is
  aiming, with no position, until a new frame solves

#### Scenario: A frame held within the window does not end the aim
- **WHEN** a frame does not solve and the last solve is within the hold
  window
- **THEN** the last position is re-sent and the cursor backend is not
  told that nothing is aiming

#### Scenario: A shorter window applies to a session already holding
- **WHEN** a session's last solve was 0.5 seconds ago and the hold
  window is changed from 0.75 to 0.25 seconds
- **THEN** that session's next unsolved frame re-sends nothing
