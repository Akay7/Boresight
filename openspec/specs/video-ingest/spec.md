# video-ingest Specification

## Purpose
Accepts camera frames from connected clients over a WebSocket, drives
each through the aim pipeline without letting a slow frame build up
lag, and reports per-session telemetry and debug geometry back to the
client and over HTTP.

## Requirements

### Requirement: Streamed camera frames drive the aim pipeline
The server SHALL expose a WebSocket endpoint that accepts camera frames
from a connected client, decodes each frame, and passes it to the same
per-frame pipeline operation used everywhere else. The aim point a
streamed frame solves to SHALL reach the OS cursor through that
session's own aim smoothing and dropout hold (see aim-smoothing and
aim-hold), and only while that session drives the cursor (see
cursor-ownership).

#### Scenario: A streamed frame moves the cursor
- **WHEN** a client that drives the cursor, or that finds it free, sends
  a frame in which enough mapped markers are visible to solve
- **THEN** the server decodes it, runs the pipeline, and the configured
  cursor backend receives one absolute move, at the session's smoothed
  aim point for that frame

#### Scenario: A streamed frame with nothing to solve moves nothing
- **WHEN** a connected client that has solved no frame within the hold
  window sends a frame containing no detectable markers
- **THEN** the cursor backend receives no call, the connection stays
  open, and the server continues accepting frames

#### Scenario: A session that does not drive the cursor moves nothing
- **WHEN** another session drives the cursor and this session sends a
  frame that solves
- **THEN** the cursor backend receives no move for it, and the frame is
  still solved and reported to this session

### Requirement: Streaming produces the same result as replaying the same frames
Streaming a sequence of frames SHALL produce the identical track of
solved aim points that replaying those same frame files through the
pipeline directly produces. The transport SHALL introduce no
transformation of its own: it decodes bytes and delegates. Smoothing
sits below the solve, at the cursor, so the solved positions reported
for each frame are the comparable quantity.

#### Scenario: Streamed fixture frames match the replayed track
- **WHEN** the frames of a checked-in rendered sequence are sent, in
  order, over the frame endpoint, with the server given time to process
  each
- **THEN** the sequence of solved positions the server reports equals
  the sequence of positions the same fixture produces when replayed
  through the pipeline directly

### Requirement: Frames are carried as self-delimiting binary messages
Each binary WebSocket message SHALL carry exactly one frame: an 8-byte
little-endian client timestamp in milliseconds, followed by the frame
encoded as JPEG. Text messages on the same connection SHALL be reserved
for JSON control and telemetry, so a later addition such as the trigger
event needs no second connection and no change to frame handling.

#### Scenario: A well-formed frame message is accepted
- **WHEN** a client sends a binary message consisting of an 8-byte
  timestamp followed by valid JPEG bytes
- **THEN** the server processes the JPEG as one frame and retains the
  timestamp for round-trip reporting

#### Scenario: A text message is not treated as a frame
- **WHEN** a client sends a JSON text message
- **THEN** the server handles it as control or telemetry and does not
  attempt to decode it as an image

### Requirement: A malformed frame does not end the session
The server SHALL treat an undecodable or truncated frame as a lost
frame: it SHALL count it, leave the cursor untouched, keep the
connection open, and continue with the next frame. A single corrupt
frame over a lossy Wi-Fi link SHALL NOT cost the player their
connection.

#### Scenario: Undecodable frame bytes are counted and skipped
- **WHEN** a client sends a binary message whose payload is not
  decodable as an image
- **THEN** the connection remains open, the cursor backend receives no
  call, and the frame is counted as failed

#### Scenario: A binary message too short to contain a timestamp is rejected
- **WHEN** a client sends a binary message shorter than the 8-byte
  timestamp header
- **THEN** the server counts it as a failed frame and keeps the
  connection open

### Requirement: Frames that arrive faster than they can be processed are dropped, newest first
The server SHALL retain only the most recent unprocessed frame when
frames arrive faster than the pipeline can consume them, discarding any
earlier one still waiting rather than queueing. Queued frames produce a
cursor that lags further behind the player's aim the longer the session
runs; a dropped frame costs nothing, because the next one carries a
better answer. The count of dropped frames SHALL be reported rather than
hidden.

#### Scenario: A backlog collapses to the newest frame
- **WHEN** several frames arrive while the pipeline is still processing
  an earlier one
- **THEN** only the most recently arrived frame is processed next, the
  intervening frames are discarded, and the discarded count increases by
  the number skipped

#### Scenario: Receiving is not blocked by processing
- **WHEN** the pipeline is processing a frame
- **THEN** the server continues to accept incoming frames rather than
  applying backpressure to the client, so the client's own send loop
  never stalls

### Requirement: Each connection reports its own telemetry
The server SHALL report, periodically over the same connection, the
frames received, processed, dropped and failed for that connection, the
time spent decoding and solving a frame, the marker count and
conditioning of the most recent solve, and the round-trip time derived
from the client timestamp carried with each frame. Round-trip time is
the first number that has to be measured on real hardware, and the
system SHALL NOT require external tooling to obtain it.

#### Scenario: Telemetry reaches the client during a session
- **WHEN** a client has streamed frames for long enough for one
  reporting interval to elapse
- **THEN** it receives a JSON text message carrying the counts, the
  timings, and the round-trip time for that connection

#### Scenario: Counts account for every received frame
- **WHEN** a session ends after frames have been processed, dropped and
  failed
- **THEN** the processed, dropped and failed counts sum to the number of
  frames received

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

### Requirement: A session can request per-frame debug geometry
The server SHALL accept a JSON control message on the frame
connection's existing text channel by which a client turns per-frame
debug geometry on or off for its own session, and SHALL honour it from
the next processed frame onward. The setting SHALL belong to the
session rather than to the server, so one client enabling it does not
change what another client receives, and SHALL be re-settable at any
time during a session, including immediately after a reconnect.

#### Scenario: Debug geometry is enabled by a control message
- **WHEN** a connected client sends the debug control message with
  debug enabled
- **THEN** subsequent telemetry messages for that session carry the
  pipeline's debug geometry for the frame they report

#### Scenario: Debug geometry is turned off again
- **WHEN** a client that enabled debug geometry sends the control
  message with it disabled
- **THEN** subsequent telemetry messages for that session no longer
  carry the debug fields

#### Scenario: The setting does not leak between sessions
- **WHEN** one client enables debug geometry while a second client is
  streaming on its own connection
- **THEN** the second client's telemetry is unaffected

### Requirement: Telemetry is unchanged for sessions that do not ask
The telemetry payload SHALL omit the debug fields entirely — not send
them as empty or null — for any session that has not enabled debug
geometry, so that a client written against the existing payload
receives exactly what it receives today and a client that never asked
cannot render a partial overlay.

#### Scenario: A session that never asks sees the existing payload
- **WHEN** a client streams frames without ever sending the debug
  control message
- **THEN** every telemetry message it receives contains the same set of
  fields as before this change, with no debug keys present

### Requirement: Debug telemetry carries the frame's geometry and fit quality
When debug geometry is enabled, each telemetry message SHALL carry, for
the frame it reports, the decoded frame's pixel size, the detected
markers with their IDs, image-pixel corners and mapped status, and —
when that frame solved — the projected screen rectangle, the emitted
cursor position in image pixels, and the reprojection error of the fit.
The decoded size is reported rather than assumed to match the client's
capture resolution, because a browser may grant a different resolution
than the one requested and a silent mismatch would displace every drawn
shape.

#### Scenario: A solved frame reports full geometry
- **WHEN** a session with debug geometry enabled sends a frame that
  solves
- **THEN** its telemetry message carries the decoded image size, the
  detections, the projected screen rectangle, the cursor position in
  image pixels, and the reprojection error

#### Scenario: An unsolved frame reports what there was
- **WHEN** a session with debug geometry enabled sends a frame that
  does not solve
- **THEN** its telemetry message carries the decoded image size and any
  detections, and carries no rectangle, cursor position or reprojection
  error from that or any previous frame

#### Scenario: Reprojection error accompanies the conditioning flag
- **WHEN** a telemetry message reports a solved frame with debug
  geometry enabled
- **THEN** it carries the reprojection error in addition to, not in
  place of, the existing conditioning flag for that solve

### Requirement: A session can identify its client kind
The server SHALL accept a `hello` JSON control message on the frame
connection's text channel carrying the client kind and, optionally, its
software version and capture resolution, and SHALL attach that identity
to the session for its logs and its entry in the session listing. A
session that never sends `hello` SHALL be served exactly as before and
labelled as unidentified. A malformed `hello` SHALL be ignored without
closing the connection, and SHALL NOT affect frame handling.

#### Scenario: An identified session is logged by kind
- **WHEN** a client sends `hello` with client kind `esp32-cam` and then
  streams frames
- **THEN** the server's connection, periodic and disconnection log lines
  for that session name the client kind

#### Scenario: A session that never says hello is unaffected
- **WHEN** a client streams frames without sending `hello`
- **THEN** frames are processed and reported exactly as before, and the
  session is listed as unidentified

#### Scenario: A malformed hello is ignored
- **WHEN** a client sends a `hello` message with a missing or non-string
  client kind
- **THEN** the connection stays open, the session remains unidentified,
  and subsequent frames are processed normally

### Requirement: Active sessions' telemetry is readable over HTTP
The server SHALL serve a listing of the currently active frame sessions,
each with its client identity, its remote address, how long it has been
connected, and the same telemetry fields most recently sent to that
client over its own socket, excluding debug geometry. A client with no
display of its own cannot show its telemetry, so it SHALL be observable
from another device. A session SHALL disappear from the listing once its
connection ends, and the listing SHALL be covered by the same token
requirement as every other endpoint.

#### Scenario: A streaming session appears in the listing
- **WHEN** a client is connected and has streamed frames, and the session
  listing is requested
- **THEN** the listing contains that session with its client kind,
  connection age, frame counts, round-trip time and most recent outcome

#### Scenario: A closed session leaves the listing
- **WHEN** a client disconnects and the listing is requested afterwards
- **THEN** that session is no longer present

#### Scenario: Debug geometry is not exposed in the listing
- **WHEN** a session with debug geometry enabled is listed
- **THEN** its listing entry carries no debug geometry

#### Scenario: The listing requires the token
- **WHEN** a token is configured and the listing is requested without it
- **THEN** the request is refused

### Requirement: Aim smoothing is timed by the client's capture timestamps
The server SHALL time aim smoothing for a session's frames by the
timestamps the client stamped on them, so that the interval the
smoothing uses between two frames is the interval between their
captures, not between their arrivals. Client timestamps SHALL only be
compared with other timestamps from the same session, never with the
server's clock or another session's. When a frame's timestamp is not a
finite number, is not later than the previous processed frame's, or is
more than one second after it, the server SHALL time that frame by its
own clock instead, so the interval used is always positive and bounded.

#### Scenario: Network jitter does not change the smoothing interval
- **WHEN** a client sends frames captured exactly 50 ms apart, and they
  reach the server at uneven intervals
- **THEN** the smoothing treats consecutive frames as 50 ms apart

#### Scenario: A repeated timestamp falls back to the server clock
- **WHEN** a client sends two consecutive frames with the same timestamp
- **THEN** the second frame is timed by the server's clock, with a
  positive interval, and the session continues normally

#### Scenario: A clock jump falls back to the server clock
- **WHEN** a client's timestamps jump backwards, or forwards by more
  than a second, between two frames
- **THEN** that frame is timed by the server's clock, and later frames
  are timed by client timestamps again, measured from the frame after
  the jump

#### Scenario: Sessions do not share a timeline
- **WHEN** two clients whose clocks have unrelated epochs stream at the
  same time
- **THEN** neither session's timestamps affect how the other's frames
  are timed
