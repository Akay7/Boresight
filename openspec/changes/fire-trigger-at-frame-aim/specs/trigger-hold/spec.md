## MODIFIED Requirements

### Requirement: Trigger press and release messages hold the primary button
The server SHALL treat `{"type": "trigger", "state": "down"}` on the
frame WebSocket as pressing and holding the primary button — at the
cursor's current position, or, when the message carries `frame_ms`, at
the aim point of the frame it names (see trigger-emission) — and
`{"type": "trigger", "state": "up"}` as releasing it. Cursor movement
produced by frames processed while the button is held SHALL move the
cursor with the button still down, so the OS sees a drag. A `down` from
a session already holding, or an `up` from a session not holding, SHALL
have no effect. A trigger message whose `state` is present but neither
`down` nor `up` SHALL be ignored. A session's trigger messages SHALL
take effect in the order they were sent, so an `up` arriving while that
session's `down` still waits for its frame SHALL release only after the
press.

#### Scenario: Press, move, release is a drag
- **WHEN** a client sends `down`, then frames that move the aim point,
  then `up`
- **THEN** the backend presses the button once, moves the cursor with it
  held, and releases it once

#### Scenario: A repeated down does not press twice
- **WHEN** a client sends `down` twice without an `up` between them
- **THEN** the button is pressed once

#### Scenario: An up without a down does nothing
- **WHEN** a client that is not holding sends `up`
- **THEN** no release is emitted

#### Scenario: An unknown state is ignored
- **WHEN** a client sends `{"type": "trigger", "state": "sideways"}`
- **THEN** nothing is pressed, released or clicked, and the session
  continues

#### Scenario: A quick tap waiting for its frame keeps its order
- **WHEN** a client sends `down` naming a frame not yet processed,
  immediately followed by `up`
- **THEN** the button is pressed at that frame's aim point and then
  released, in that order
