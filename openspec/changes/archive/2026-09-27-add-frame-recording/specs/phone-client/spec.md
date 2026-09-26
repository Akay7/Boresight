## ADDED Requirements

### Requirement: The phone can save the last seconds of its stream
The client SHALL offer a control, available while streaming, that asks
the server to save this session's recent frames as a recording, and
SHALL display the directory the server reports having written and how
many frames it holds, or the reason the server gives for writing
nothing. The control SHALL send no credentials of its own: it rides the
already-authenticated frame connection.

#### Scenario: Saving shows where the recording went
- **WHEN** the operator presses the save control while streaming
- **THEN** the page shows the recording's directory and frame count once
  the server answers

#### Scenario: A refused save is explained
- **WHEN** the server answers that nothing was recorded
- **THEN** the page shows the server's reason rather than appearing to
  have saved
