## MODIFIED Requirements

### Requirement: A trigger control message fires a click
The server SHALL treat a `{"type": "trigger"}` JSON text message on the
frame WebSocket as a request to click, and SHALL invoke the cursor
backend's click operation exactly once per such message received,
except while the primary button is already held down (see
trigger-hold), when there is nothing further to press. Without a
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

## ADDED Requirements

### Requirement: A trigger fires at the aim point of the frame it names
A trigger message MAY carry `frame_ms`, the timestamp the client stamped
on the frame the shot was aimed with. The server SHALL remember the
unsmoothed solved aim point of each of the session's recently processed
frames, keyed by that timestamp. For a trigger naming a frame, the
server SHALL, once that frame (or a later one) has been processed, move
the cursor to the unsmoothed aim point of the solved frame nearest the
named timestamp and within 100 ms of it, and then press there. Later
frames SHALL be smoothed as before. If no such solved frame exists, the
trigger SHALL act where the cursor currently is. The server SHALL NOT
wait more than 250 ms for the named frame; past that it SHALL act with
what it has. A `frame_ms` that is not a finite number SHALL be treated
as absent. The cursor SHALL NOT be moved for a trigger that presses
nothing because the button is already held.

#### Scenario: A shot during a fast swing lands at the frame's aim
- **WHEN** the smoothed cursor trails the aim during a swing and the
  client sends a trigger naming the latest frame it sent
- **THEN** the click lands at that frame's unsmoothed aim point, not at
  the trailing cursor position

#### Scenario: A shot waits for its frame to be processed
- **WHEN** a trigger names a frame the server has received but not yet
  processed
- **THEN** the click happens after that frame is processed, at its aim
  point

#### Scenario: A shot whose frame did not solve fires in place
- **WHEN** a trigger names a frame in which no markers were found and
  no nearby frame solved
- **THEN** the click happens where the cursor already is

#### Scenario: A shot naming a frame that never arrives is not lost
- **WHEN** a trigger names a frame that the server never processes
- **THEN** the click still happens, where the cursor is, no later than
  250 ms after the trigger arrived

#### Scenario: A legacy trigger is unchanged
- **WHEN** a client sends a trigger without `frame_ms`
- **THEN** the click happens immediately where the cursor is, as before
