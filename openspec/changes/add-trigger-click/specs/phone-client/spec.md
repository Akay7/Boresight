## ADDED Requirements

### Requirement: An on-screen trigger sends a click event per press
The client SHALL display a trigger control that, on each press, sends
one trigger message over the existing frame connection, requiring no
second connection or endpoint. The control SHALL be disabled until
streaming has started, since there is no connection to send it on
before then.

#### Scenario: Pressing the trigger sends one message
- **WHEN** the client is streaming and the player presses the trigger
  control
- **THEN** the client sends one trigger message on the existing frame
  WebSocket connection

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
