## MODIFIED Requirements

### Requirement: Disconnection leaves no motion and no leaked work
The server SHALL treat a closed or dropped connection as the end of that
session: it SHALL stop processing that connection's frames, SHALL NOT
emit any further cursor movement on its behalf, SHALL release a primary
button the session was holding, and SHALL release the resources
associated with it. It SHALL NOT move the cursor to a remembered or
extrapolated position after the client is gone.

#### Scenario: A closed connection stops moving the cursor
- **WHEN** a streaming client disconnects, cleanly or abruptly
- **THEN** no further cursor movement is emitted for that connection and
  its processing task ends

#### Scenario: A closed connection releases its held button
- **WHEN** a client that is holding the trigger disconnects, cleanly,
  abruptly, or because frame processing stopped
- **THEN** the server releases the button

#### Scenario: A second connection starts clean
- **WHEN** a client connects after a previous session has ended
- **THEN** its telemetry counts start from zero and are not carried over
  from the previous connection
