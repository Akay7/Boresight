## ADDED Requirements

### Requirement: Frame timestamps mark the moment of capture
The client SHALL stamp each frame with the time the camera captured it,
taken from the browser's per-video-frame capture metadata where
available and otherwise from the client's monotonic clock at the moment
the frame is taken from the video element. The stamp SHALL NOT be taken
after the frame has been encoded, since encoding time varies from frame
to frame. The client SHALL NOT send a frame whose capture stamp equals
that of the frame it sent before, since it is the same picture.

#### Scenario: Encoding time does not enter the timestamp
- **WHEN** the client captures a frame and JPEG encoding it takes a
  variable amount of time
- **THEN** the timestamp sent with the frame is the capture time, and is
  unaffected by how long encoding took

#### Scenario: The same camera frame is not sent twice
- **WHEN** the capture timer fires again before the camera has
  delivered a new frame
- **THEN** the client sends nothing for that tick
