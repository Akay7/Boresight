## MODIFIED Requirements

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
