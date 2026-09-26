## MODIFIED Requirements

### Requirement: Disconnection leaves no motion and no leaked work
The server SHALL treat a closed or dropped connection as the end of that
session: it SHALL stop processing that connection's frames, SHALL NOT
emit any further cursor movement on its behalf, SHALL release a primary
button the session was holding, SHALL give up the cursor if the session
owned it, and SHALL release the resources associated with it. It SHALL
NOT move the cursor to a remembered or extrapolated position after the
client is gone. This SHALL hold for a frame that was already being
processed when the connection closed: that frame MAY finish, but its
aim SHALL NOT move the cursor or give the ended session the cursor
again. Ending a session SHALL NOT itself raise an error: a disconnect
racing with frame processing, or the server cancelling the session
while it winds down, SHALL end the session the same way a quiet
disconnect does.

#### Scenario: A closed connection stops moving the cursor
- **WHEN** a streaming client disconnects, cleanly or abruptly
- **THEN** no further cursor movement is emitted for that connection and
  its processing task ends

#### Scenario: A frame still being processed at disconnect does not move the cursor
- **WHEN** a client disconnects while one of its frames is still being
  processed, and that frame then solves to an aim point
- **THEN** the cursor does not move to that aim point, and the cursor is
  free for the next session to take

#### Scenario: A closed connection releases its held button
- **WHEN** a client that is holding the trigger disconnects, cleanly,
  abruptly, or because frame processing stopped
- **THEN** the server releases the button

#### Scenario: Ending a session mid-frame raises no error
- **WHEN** a client disconnects while a frame is being processed, and
  the session is cancelled while it winds down
- **THEN** the session ends without an error escaping it, the held
  button and the cursor are released, and the session is no longer
  listed

#### Scenario: A second connection starts clean
- **WHEN** a client connects after a previous session has ended
- **THEN** its telemetry counts start from zero and are not carried over
  from the previous connection
