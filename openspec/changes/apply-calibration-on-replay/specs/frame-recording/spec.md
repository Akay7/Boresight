## ADDED Requirements

### Requirement: A recording carries the calibration it was made with
A recording's manifest SHALL carry the session's lens model and zero in
effect when it was saved, or none for either the session did not have,
so that replaying it reproduces the aim the session produced live.

#### Scenario: A zeroed, calibrated session is saved
- **WHEN** a session with a lens model and a zero saves a recording
- **THEN** the manifest holds both, in the form the lens and zeroing
  stores use

#### Scenario: A zeroed session's recording replays to its live aim
- **WHEN** a zeroed session's frames are saved and the recording is
  replayed
- **THEN** the replayed track equals the aim the session emitted live
