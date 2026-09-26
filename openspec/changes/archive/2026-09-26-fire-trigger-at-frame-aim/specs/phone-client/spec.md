## ADDED Requirements

### Requirement: The trigger names the frame it was aimed with
When the on-screen trigger is pressed, the client SHALL include in its
`down` message a `frame_ms` field holding the timestamp of the latest
frame it has sent on the current connection, so the server can fire at
that frame's aim point rather than at the smoothed cursor. If no frame
has been sent on the connection yet, the client SHALL omit the field.

#### Scenario: A press names the latest sent frame
- **WHEN** the client has sent frames and the player presses the
  trigger
- **THEN** the `down` message carries the timestamp of the most recent
  frame sent

#### Scenario: A press before any frame names none
- **WHEN** the player presses the trigger before any frame has been
  sent on the connection
- **THEN** the `down` message carries no `frame_ms`
