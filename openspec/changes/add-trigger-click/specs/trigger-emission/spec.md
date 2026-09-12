## ADDED Requirements

### Requirement: A trigger control message fires a click
The server SHALL treat a `{"type": "trigger"}` JSON text message on the
frame WebSocket as a request to click at the cursor's current position,
and SHALL invoke the cursor backend's click operation exactly once per
such message received. The click carries no position of its own — it
fires wherever the most recently processed frame last placed the
cursor — since the trigger and the aim point travel as independent
events on the same connection.

#### Scenario: A trigger message invokes a click
- **WHEN** a connected client sends `{"type": "trigger"}` as a text
  message on the frame WebSocket
- **THEN** the server invokes the cursor backend's click operation once

#### Scenario: Repeated trigger messages each produce a click
- **WHEN** a connected client sends `{"type": "trigger"}` three times
- **THEN** the cursor backend's click operation is invoked three times,
  once per message

#### Scenario: A trigger message does not disturb frame handling
- **WHEN** a client interleaves `{"type": "trigger"}` messages with
  binary frame messages on the same connection
- **THEN** frames are still decoded, solved, and reported exactly as
  they would be without the trigger messages present

### Requirement: Trigger events are counted in session telemetry
The server SHALL count trigger messages received in the same
per-connection telemetry the frame-processing counters already use, and
SHALL include the count in every stats message sent back, so the phone
can confirm a tap actually reached the server.

#### Scenario: The trigger count is reported back
- **WHEN** a client has sent two trigger messages on a connection
- **THEN** every subsequent stats message reports a trigger count of
  two
