## MODIFIED Requirements

### Requirement: A trigger control message fires a click
The server SHALL treat a `{"type": "trigger"}` JSON text message on the
frame WebSocket as a request to click, and SHALL invoke the cursor
backend's click operation exactly once per such message received,
except while the primary button is already held down (see
trigger-hold), when there is nothing further to press, and except while
the sending session is zeroing (see boresight-calibration), when the
trigger records a calibration shot and clicks nothing. Without a
`frame_ms` field the click carries no position of its own — it fires
wherever the most recently processed frame last placed the cursor. With
a `frame_ms` field, the click fires at the aim point of that frame (see
"A trigger fires at the aim point of the frame it names").

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

#### Scenario: A trigger while zeroing does not click
- **WHEN** a session that is zeroing sends `{"type": "trigger"}` or a
  `down`
- **THEN** the cursor backend's click and press operations are not
  invoked, and the trigger count is unchanged
