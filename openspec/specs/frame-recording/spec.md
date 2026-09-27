# frame-recording Specification

## Purpose
Lets an operator save the last few seconds of a live frame session --
the frames, their timing, the trigger presses and the layout they were
solved against -- in the replay format the test harness already reads,
so a misbehaviour seen on real hardware becomes a reproducible capture.

## Requirements

### Requirement: Each session keeps a bounded buffer of its recent frames
While recording is enabled, each frame session SHALL retain the frames it
received over a configurable window of seconds, oldest evicted first, and
SHALL never hold more than a configurable number of bytes of frame data,
evicting the oldest frames to stay under it. Each retained frame SHALL
keep the client capture timestamp it arrived with, when the server
received it, and, once processed, the outcome and emitted position the
live pipeline produced for it, or that it was dropped unprocessed. The
buffer SHALL also retain the trigger events the session sent within the
same window. Buffering SHALL NOT copy, decode or re-encode frame data.
With recording disabled, no buffer SHALL exist and frame handling SHALL
be unchanged.

#### Scenario: Frames older than the window are evicted
- **WHEN** a session has streamed for longer than the configured window
- **THEN** its buffer holds only frames received within that window

#### Scenario: The byte cap evicts before the window does
- **WHEN** the frames received within the window exceed the configured
  byte cap
- **THEN** the oldest frames are evicted until the retained frame data
  is within the cap

#### Scenario: Recording disabled keeps nothing
- **WHEN** the server is started with a recording window of zero
- **THEN** sessions retain no frames, and a request to save a recording
  is answered with a reason rather than a directory

### Requirement: A session's buffer is saved on request
A frame session SHALL save its buffer when its client sends a record
control message on the frame connection, and SHALL answer on that same
connection with the directory it wrote and the number of frames saved,
or with the reason nothing was written. The server SHALL also offer an
HTTP endpoint, subject to the same token requirement as every other
endpoint, that saves the buffer of every live session and lists what it
wrote, so a client with no screen can be recorded from another device.
Saving SHALL NOT stop, pause or reset the session or its buffer.

#### Scenario: A record message saves the sending session
- **WHEN** a streaming client sends a record control message
- **THEN** a new recording directory holding that session's buffered
  frames is written, and the client receives a message naming it and
  its frame count

#### Scenario: Saving with nothing buffered writes nothing
- **WHEN** a record message arrives before the session has received any
  frame
- **THEN** no directory is written and the client is told why

#### Scenario: The HTTP endpoint requires the token
- **WHEN** the save endpoint is called without a valid token while one
  is configured
- **THEN** the request is refused and nothing is written

### Requirement: A recording is a replayable frame sequence
A recording SHALL be written to its own new directory under
`.boresight/recordings/`, named by the time it was saved, holding each
frame's JPEG bytes exactly as received and a manifest in the format the
checked-in fixture sequences use: the image size, the screen size in
millimetres, the marker size and each marker's position in millimetres,
and an ordered list of frames naming their files. It SHALL also hold the
full marker layout that was in use as a layout file the server and the
replay entry point accept. The manifest SHALL additionally carry each
frame's client timestamp and live result, the trigger events, the marker
source and on-screen overlay geometry in effect, and the client's
self-reported identity. Frames solved against a different layout than
the newest frame's SHALL be left out and counted, since no single layout
file could replay them.

#### Scenario: A recording replays through the existing harness
- **WHEN** a sequence of fixture frames is streamed, saved as a
  recording, and the recording directory is replayed through the
  pipeline with its own layout file
- **THEN** the replayed track equals the track produced by replaying the
  original fixture frames

#### Scenario: Frames are stored byte for byte
- **WHEN** a recording is saved
- **THEN** each frame file is identical to the JPEG payload the client
  sent for it

### Requirement: No recorded file contains the access token
A recording SHALL NOT contain the server's access token in any file it
writes, however the client authenticated, and SHALL NOT store raw
control messages; trigger events are recorded as their parsed fields
only.

#### Scenario: A recording made under a token is free of it
- **WHEN** a recording is saved from a session authenticated with a token
- **THEN** no file in the recording directory contains the token's value

### Requirement: A recording carries the calibration it was made with
A recording's manifest SHALL carry the session's lens model and zero in
effect when it was saved, or none for either the session did not have,
so that replaying it reproduces the aim the session produced live.

#### Scenario: A zeroed, calibrated session is saved
- **WHEN** a session with a lens model and a zero saves a recording
- **THEN** the manifest holds both, in the form the lens and zeroing
  stores use

#### Scenario: A zeroed session's recording replays to its live aim
- **WHEN** a zeroed session's frames are saved and the recording is
  replayed
- **THEN** the replayed track equals the aim the session emitted live
