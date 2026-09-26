## ADDED Requirements

### Requirement: The client can zero the gun
The client SHALL offer controls to start zeroing, finish it, cancel it
and reset a stored zero, sending the corresponding zeroing control
messages on the frame connection. While a run is active it SHALL show
which target to shoot, its position in the sequence, whether it is
optional, and the outcome of the last shot. When the session is zeroed
it SHALL say so, with the fit's residual. The trigger SHALL keep working
unchanged; the server decides that a press during zeroing is a shot.

#### Scenario: The prompt names the target to shoot
- **WHEN** a zeroing run is active and the server reports the target
  "top-left corner"
- **THEN** the client shows that label and the target's position in the
  sequence

#### Scenario: Controls are unavailable without a connection
- **WHEN** the client is not streaming
- **THEN** the zeroing controls are disabled

### Requirement: The client sends a persistent identity
The client SHALL generate a random identifier once, keep it in the
browser's local storage, and include it as `id` in every `hello`, so the
server can recognise the same phone across reconnects and server
restarts. Where local storage is unavailable the `hello` SHALL be sent
without an `id`.

#### Scenario: The same id is sent after a reload
- **WHEN** the page is reloaded and streaming restarted
- **THEN** the `hello` carries the same `id` as before
