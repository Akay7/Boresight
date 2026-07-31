# video-ingest Specification

## Purpose
TBD - created by archiving change add-phone-video-stream. Update Purpose after archive.
## Requirements
### Requirement: Streamed camera frames drive the aim pipeline
The server SHALL expose a WebSocket endpoint that accepts camera frames
from a connected client, decodes each frame, and passes it to the same
per-frame pipeline operation used everywhere else, so that a frame
arriving over the network moves the OS cursor exactly as a frame read
from disk does.

#### Scenario: A streamed frame moves the cursor
- **WHEN** a client connected to the frame endpoint sends a frame in
  which enough mapped markers are visible to solve
- **THEN** the server decodes it, runs the pipeline, and the configured
  cursor backend receives one absolute move at the solved position

#### Scenario: A streamed frame with nothing to solve moves nothing
- **WHEN** a connected client sends a frame containing no detectable
  markers
- **THEN** the cursor backend receives no call, the connection stays
  open, and the server continues accepting frames

### Requirement: Streaming produces the same result as replaying the same frames
Streaming a sequence of frames SHALL produce the identical cursor track
that replaying those same frame files through the pipeline directly
produces. The transport SHALL introduce no transformation of its own: it
decodes bytes and delegates.

#### Scenario: Streamed fixture frames match the replayed track
- **WHEN** the frames of a checked-in rendered sequence are sent, in
  order, over the frame endpoint to a server using a recording cursor
  backend, with the server given time to process each
- **THEN** the recorded sequence of cursor positions equals the sequence
  the same fixture produces when replayed through the pipeline directly

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
emit any further cursor movement on its behalf, and SHALL release the
resources associated with it. It SHALL NOT move the cursor to a
remembered or extrapolated position after the client is gone.

#### Scenario: A closed connection stops moving the cursor
- **WHEN** a streaming client disconnects, cleanly or abruptly
- **THEN** no further cursor movement is emitted for that connection and
  its processing task ends

#### Scenario: A second connection starts clean
- **WHEN** a client connects after a previous session has ended
- **THEN** its telemetry counts start from zero and are not carried over
  from the previous connection
