## Why

When the aim misbehaves on real hardware -- a jump, a lost lock, a shot
that lands in the wrong place -- the only evidence is a description of
it. The checked-in fixtures show the value of a replayable capture
(README: "Replaying a fixed capture turns 'it feels worse now' into a
number"), but there is no way to produce one from a live session. A
button that saves what the server just saw, in the format the replay
harness already reads, turns a bug report into a regression test.

## What Changes

- Each frame session keeps a bounded, in-memory ring buffer of the
  frames it received over the last N seconds (configurable, capped in
  bytes), together with their client capture timestamps, the trigger
  events it was sent, and what the live pipeline made of each frame.
  Buffering holds references to bytes the server already received; with
  recording disabled (`--record-seconds 0`) no buffer exists at all.
- A new WebSocket control message, `{"type": "record"}`, dumps the
  sending session's buffer to `.boresight/recordings/<timestamp>/` and
  answers with a `{"type": "recording", ...}` message naming the saved
  directory and frame count. An authenticated `POST /recordings` does the
  same for every live session, for a client with no screen (ESP32-CAM).
- A recording is the existing fixture layout: `frame_NNNN.jpg` files and
  a `manifest.json` with `image_size`, `screen_size_mm`,
  `marker_size_mm`, `marker_layout_mm` and an ordered `frames` list, plus
  a `markers.toml` holding the exact layout that was in use, so
  `pipeline.replay()` and `python -m boresight.pipeline` read it
  unchanged. Recording-only metadata (client timestamps, trigger events,
  the live outcome per frame, the marker source and overlay geometry,
  the client's `hello`) sits alongside in the same manifest.
- `python -m boresight.pipeline <dir>` uses the directory's own
  `markers.toml` when it has one and `--config` is not given.
- The phone page gets a "Save last N s" button that sends the message
  and shows the saved path, or the reason nothing was saved.
- Nothing recorded contains the access token.

## Capabilities

### New Capabilities
- `frame-recording`: per-session rolling frame buffer, the dump
  triggers, the on-disk recording format, and its replayability.

### Modified Capabilities
- `phone-client`: adds a control that saves a recording and reports
  where it went.
- `aim-pipeline`: the replay entry point prefers a sequence's own
  layout file.

## Impact

- New `src/boresight/recording.py`; small hooks in `server.py`
  (session buffer, control message, route, CLI flags), a read-only
  `marker_map` property on `AimPipeline`, the replay CLI default.
- `web/index.html` and `web/capture.js`: one button, one message
  handler.
- Memory: up to `--record-max-mb` (default 64 MB) per streaming session
  while recording is enabled; nothing when disabled.
- Disk: recordings written under `.boresight/` (already gitignored) in
  the server's working directory, only on request.
