## Purpose

Lets a client hold the primary button down and release it later, so the
trigger can drag as well as click, while guaranteeing the server never
leaves the button stuck down.

## ADDED Requirements

### Requirement: Trigger press and release messages hold the primary button
The server SHALL treat `{"type": "trigger", "state": "down"}` on the
frame WebSocket as pressing and holding the primary button at the
cursor's current position, and `{"type": "trigger", "state": "up"}` as
releasing it. Cursor movement produced by frames processed while the
button is held SHALL move the cursor with the button still down, so the
OS sees a drag. A `down` from a session already holding, or an `up` from
a session not holding, SHALL have no effect. A trigger message whose
`state` is present but neither `down` nor `up` SHALL be ignored.

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

### Requirement: A plain trigger message is still one click
A trigger message without a `state` field SHALL keep its existing
meaning: one click at the cursor's current position. Clients that never
send `state` SHALL behave exactly as before this change.

#### Scenario: A legacy client still clicks
- **WHEN** a client sends `{"type": "trigger"}`
- **THEN** the backend clicks once and nothing is left held

### Requirement: Holds from several sessions share one button
The primary button SHALL be held while at least one session holds it and
released when the last holding session releases. A session's `up`, end
or timeout SHALL release only its own hold.

#### Scenario: One session's release does not end another's hold
- **WHEN** session A and session B both send `down`, then A sends `up`
- **THEN** the button stays held until B also releases

### Requirement: A held button is released when its session goes silent
The server SHALL release a session's hold when no message of any kind
(frame or text) has arrived from that session for 2 seconds, so a client
that stalls without disconnecting cannot leave the button down.

#### Scenario: A stalled client's hold is released
- **WHEN** a session sends `down` and then sends nothing for 2 seconds
  while staying connected
- **THEN** the server releases the button

#### Scenario: A streaming client can hold indefinitely
- **WHEN** a session sends `down` and keeps streaming frames for 30
  seconds
- **THEN** the button stays held for the whole 30 seconds

### Requirement: Presses are counted in trigger telemetry
The session's trigger count SHALL increase by one for each `down` that
starts a hold and for each plain click, and SHALL NOT increase for `up`
or for ignored messages, so the count is the number of presses.

#### Scenario: A press and release count once
- **WHEN** a client sends `down` then `up`
- **THEN** its reported trigger count increases by one
