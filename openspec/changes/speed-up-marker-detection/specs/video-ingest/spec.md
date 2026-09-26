## ADDED Requirements

### Requirement: Each streaming session detects through its own tracker
Each frame session SHALL detect its frames through a per-session
detector created for that session, fed only by that session's frames
and discarded when the session ends, and SHALL start a fresh one when
the marker source changes. A session's frames SHALL be decoded
directly to greyscale, the only form detection uses.

#### Scenario: Two sessions do not share tracking state
- **WHEN** two sessions are connected at once
- **THEN** each detects through a per-session detector of its own

#### Scenario: A marker-source switch starts tracking afresh
- **WHEN** the marker source changes while a session is streaming
- **THEN** that session's next frame is detected through a newly created
  per-session detector
