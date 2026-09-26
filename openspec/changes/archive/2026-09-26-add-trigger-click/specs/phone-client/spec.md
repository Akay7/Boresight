## ADDED Requirements

### Requirement: An on-screen trigger sends trigger events on the frame connection
The client SHALL display a trigger control whose presses are sent as
trigger messages over the existing frame connection, requiring no
second connection or endpoint. Which messages a press and a release send
is specified by the trigger-hold capability. The control SHALL be
disabled until streaming has started, since there is no connection to
send it on before then.

#### Scenario: Pressing the trigger uses the existing connection
- **WHEN** the client is streaming and the player presses the trigger
  control
- **THEN** the client sends its trigger message on the existing frame
  WebSocket connection, and opens no other connection

#### Scenario: The trigger is unusable before streaming starts
- **WHEN** the client has not yet started streaming
- **THEN** the trigger control is disabled and pressing it sends
  nothing

### Requirement: Trigger telemetry is visible on the phone
The client SHALL display the count of trigger events the server has
acknowledged, using the same telemetry channel other session counters
already arrive on, so the player can confirm a press reached the
server.

#### Scenario: Acknowledged trigger count is displayed
- **WHEN** the server reports a trigger count in a stats message
- **THEN** the client updates the displayed count to match
