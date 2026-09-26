## Why

Aim smoothing is timed by the server's clock at the moment a frame is
processed, so every millisecond of Wi-Fi and queueing jitter between the
camera and the server becomes a wrong `dt` in the One Euro filter, and
the filter turns it into aim jitter. The phone makes it worse: it stamps
each frame *after* JPEG encoding, so even the timestamp it sends is off
by a variable encode time. The client's clock already says, to the
millisecond, how far apart two frames were really captured.

## What Changes

- The phone stamps each frame at capture: the video frame's capture
  time from `requestVideoFrameCallback` metadata where the browser
  provides it, otherwise `performance.now()` at the moment the frame is
  drawn from the video element, never after encoding. A frame whose
  stamp equals the previous one sent (the camera has not delivered a new
  picture yet) is not sent again.
- The server times aim smoothing from those capture timestamps: the
  interval between two frames of one session is the difference of their
  client timestamps. The client's clock is only ever differenced within
  its own session, never compared with the server's.
- A timestamp that does not make sense — not a number, not later than
  the previous frame's, or implausibly far from it — is not trusted: the
  interval falls back to the server's own clock for that frame, so a
  client clock that jumps or repeats cannot stall or explode the filter.
- The ESP32-CAM firmware stamps a frame with the camera driver's
  capture time instead of the time it happened to be sent. The wire
  format is unchanged.
- Round-trip time as displayed now runs from capture rather than from
  the end of encoding, i.e. it is the latency the player actually feels.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities
- `video-ingest`: aim smoothing is timed by the client's capture
  timestamps, with a fallback for timestamps that cannot be trusted.
- `phone-client`: the frame timestamp is taken at capture, before
  encoding.

## Impact

- `src/boresight/stream.py`: a per-session capture clock that turns
  client timestamps into filter time.
- `src/boresight/one_euro.py`, `inject.py`, `pipeline.py`,
  `aim_hold.py`: a frame's time can be passed through to the filter
  instead of read from the server clock.
- `src/boresight/server.py`: the processing loop stamps each frame.
- `src/boresight/web/capture.js`: capture-time stamping.
- `firmware/boresight-cam/main/camera.c`, `camera_fake.c`, `main.c`,
  `boresight_cam.h`: the frame carries its capture time.
- Tests: `tests/test_capture_clock.py` (new), `tests/test_inject.py`,
  `tests/test_aim_hold.py`, `tests/test_stream_e2e.py`.
- Wire compatibility: unchanged. Old clients that stamp at send time
  still work; they just get less benefit.
