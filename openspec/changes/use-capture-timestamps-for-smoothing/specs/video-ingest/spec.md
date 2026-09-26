## ADDED Requirements

### Requirement: Aim smoothing is timed by the client's capture timestamps
The server SHALL time aim smoothing for a session's frames by the
timestamps the client stamped on them, so that the interval the
smoothing uses between two frames is the interval between their
captures, not between their arrivals. Client timestamps SHALL only be
compared with other timestamps from the same session, never with the
server's clock or another session's. When a frame's timestamp is not a
finite number, is not later than the previous processed frame's, or is
more than one second after it, the server SHALL time that frame by its
own clock instead, so the interval used is always positive and bounded.

#### Scenario: Network jitter does not change the smoothing interval
- **WHEN** a client sends frames captured exactly 50 ms apart, and they
  reach the server at uneven intervals
- **THEN** the smoothing treats consecutive frames as 50 ms apart

#### Scenario: A repeated timestamp falls back to the server clock
- **WHEN** a client sends two consecutive frames with the same timestamp
- **THEN** the second frame is timed by the server's clock, with a
  positive interval, and the session continues normally

#### Scenario: A clock jump falls back to the server clock
- **WHEN** a client's timestamps jump backwards, or forwards by more
  than a second, between two frames
- **THEN** that frame is timed by the server's clock, and later frames
  are timed by client timestamps again, measured from the frame after
  the jump

#### Scenario: Sessions do not share a timeline
- **WHEN** two clients whose clocks have unrelated epochs stream at the
  same time
- **THEN** neither session's timestamps affect how the other's frames
  are timed
