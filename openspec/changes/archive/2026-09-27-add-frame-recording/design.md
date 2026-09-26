## Context

A frame session (`server.run_frame_session`) receives binary frames,
splits off the client timestamp (`stream.unpack_frame`) and drops them
into a one-deep `FrameSlot`; a processor task solves the newest through
the session's `SessionPipeline`. Text messages on the same socket are
control (`_handle_control`): `hello`, `rtt`, `trigger`, `debug`.

The replay harness (`pipeline.replay`, `python -m boresight.pipeline`,
`tests/test_stream_e2e.py`, `tests/test_solve_video_e2e.py`) reads a
directory of JPEG frames plus a `manifest.json` whose `frames` list gives
the order. The fixture manifests also carry `image_size`,
`screen_size_mm`, `marker_size_mm` and `marker_layout_mm`, which the
solve-level tests read directly. The layout the live server solves
against can be the shipped file, a user file, or one derived from the
on-screen overlay's geometry, and can change mid-session when the
marker source is switched. `markers.layout_toml` already serializes a
`MarkerMap` into a `markers.toml` that `load_marker_map` reads back.

Several other changes are in flight against `server.py`, `capture.js`
and `index.html`, so the hooks there are kept small and additive.

## Goals / Non-Goals

**Goals:**
- A recording directory is a drop-in replay fixture: `replay(dir, ...)`
  and the CLI run it with no conversion step.
- Buffering is cheap enough to leave on by default.
- A recording carries enough context to be a useful bug report on its
  own: timing, triggers, live results, layout, client identity.

**Non-Goals:**
- Continuous recording to disk, or recording longer than memory allows.
- Replaying trigger events or client timing through the server's
  session machinery. The harness replays frames through the pipeline;
  the extra metadata is for humans and for tests that want it.
- Ground truth. A live recording has no `aim_point_screen_mm`; tests
  built on one assert against a replayed track, not a rendered truth.
- A recordings browser or download endpoint. The files are on the PC
  running the server; that is where a bug report is filed from.

## Decisions

### A per-session ring buffer of references, in its own module

`recording.py` holds `FrameRecorder` (one per session) and the writer.
The receive loop calls `recorder.frame(client_ms, jpeg, layout)` after
`unpack_frame`; that appends a small entry holding a reference to the
JPEG `bytes` object the server already has, then evicts from the left
while the oldest is older than the window or the retained byte total is
over the cap. A `deque` makes both O(1) amortised. No copy, no decode:
the only cost while buffering is an append, a few comparisons, and the
memory the cap allows. Disabled (`--record-seconds 0`) means the session
gets `None` instead of a recorder, and every hook is behind an
`if recorder is not None`.

Alternative: record in the `FrameSlot`. Rejected -- the slot's whole
point is to forget, and a dropped frame is still worth recording (it is
what the client sent).

Defaults: 10 s and 64 MB. At the phone's 20 fps and ~60-100 KB frames
that is 12-20 MB, so the window binds, and the cap only matters for a
misconfigured client streaming huge frames.

### Live results are attached by timestamp, not by identity through the slot

The processor learns a frame's result after the slot handed it over.
Rather than threading an entry object through `FrameSlot` (shared code
other changes touch), the processor calls
`recorder.result(client_ms, outcome, position)`, which searches the
buffer from the newest end for that timestamp -- almost always the last
entry or one before it. A frame never annotated is written as
`"live": {"outcome": "dropped"}` (or `"pending"` if it is the newest and
still in flight when saved).

### Trigger events are parsed, never stored raw

`recorder.control(text)` is called for each text message; it parses the
JSON and keeps only `trigger` messages, as `{state, frame_ms,
received_s}`, and the latest `hello`'s `client`, `version`,
`frame_size`. Raw text is never retained. This is what keeps the token
out: it never travels in a frame or a control message (it is in the
handshake's query string, cookie or header), and the recorder sees only
those. A test asserts it anyway, on every file written.

### The layout is captured per frame as a reference

Each entry holds the `MarkerMap` the session's pipeline was using when
the frame arrived (`controller.pipeline.marker_map`, a new read-only
property on `AimPipeline`). Saving uses the newest frame's layout and
drops any older frame whose layout is a different object, recording how
many were omitted. A marker-source switch inside the window therefore
yields a recording that replays correctly rather than one that is
silently solved against the wrong tags.

### Writing: the fixture format, plus `markers.toml`, plus extras

`.boresight/recordings/<YYYYmmdd-HHMMSS[-N]>/` relative to the server's
working directory, next to the certificate `.boresight/` already holds
(and already gitignored). A collision appends a counter; the directory is
created with `exist_ok=False` so two saves in one second never merge.
Contents:

- `frame_0001.jpg` ... -- the payloads, byte for byte.
- `markers.toml` -- `markers.layout_toml(layout)`.
- `manifest.json` -- the fixture keys (`image_size` from decoding the
  newest frame's header once, at save time; `screen_size_mm`;
  `marker_layout_mm`; `marker_size_mm`, the common size, or the most
  common one when sizes differ, the full truth being in `markers.toml`;
  `frames` with `frame` and `file`), plus `recording`: format version,
  saved-at time, window and cap, `marker_source` (the controller's
  source and overlay geometry), `client`, `omitted_frames`, and per-frame
  `client_ms`, `received_s` (seconds since the first saved frame arrived) and `live`;
  `triggers` alongside.

Writing is done on a worker thread (`asyncio.to_thread`) so a save of a
few hundred frames does not stall the event loop. The buffer is
snapshotted (a list copy of references) on the loop first, so frames
arriving during the write neither block nor corrupt it.

### Triggers: a socket message for the phone, an HTTP route for the rest

`{"type": "record"}` on the frame socket saves *that* session -- it is
already authenticated, and it identifies the session without an ID
scheme. The answer is `{"type": "recording", "path", "frames"}` or
`{"type": "recording", "error"}`; the phone's telemetry handler already
ignores types it does not know, so older pages are unaffected.
`POST /recordings` saves every live session that has a recorder (for an
ESP32-CAM, from a laptop with `curl`), protected by the existing token
middleware like every other route. The session registry is untouched:
each session registers its recorder in a
small dict on `app.state` keyed by the `ActiveSession`.

### Session context: lens and zero are saved, not yet replayed

A session may undistort its frames with a calibrated lens and offset its
aim with a zero. Both are written into the manifest
(`recording.session`: `camera`, `lens`, `zero`, each as its own
`as_dict()`), read from the session when the save happens.
`pipeline.replay()` does not apply either yet, so a recording made with
a lens or zero replays the uncorrected solve; making it apply them is
future work, and the manifest already holds what it would need.

### Off in `create_app`, on in `main()`

`create_app()` without a `recording` argument keeps nothing, like the
in-memory lens store and zeroing path: an app built for a test buffers
no frames and can write nothing under the working directory.
`python -m boresight.server` passes the flags, whose default window is
10 s.

### The replay CLI prefers the directory's layout

`--config` defaults to `None`; when omitted, `<frames_dir>/markers.toml`
is used if it exists, else the shipped layout. The fixtures carry no
`markers.toml`, so their behaviour is unchanged.

## Risks / Trade-offs

- [Memory: 64 MB per session by default] -> Bounded by the cap, sessions
  are few (one phone, maybe one ESP32), and `--record-seconds 0` removes
  it entirely.
- [A recording can contain whatever the camera saw, e.g. a room] ->
  Written only on an explicit request, locally, under a gitignored
  directory; README says so.
- [`received_s`/`client_ms` are relative clocks] -> Documented in the
  manifest as what they are; nothing replays them as wall time.
- [The live result is the smoothed pipeline's emitted position, the
  replay's is the stateless one's] -> The manifest labels it `live`; the
  equality test compares replayed tracks, not live against replay.

## Open Questions

- Whether a recording should also be downloadable from the phone (a zip
  endpoint). Deferred; it would need its own auth and size thinking.
