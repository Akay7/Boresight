## Context

Every frame message already starts with an 8-byte client timestamp
(`stream.py`), but the server uses it only as an opaque echo for
round-trip time. Smoothing happens in `SmoothingCursorBackend`
(`inject.py`), whose `OneEuroFilter` reads `time.monotonic()` when a
move arrives. That move is made from inside `AimPipeline.process_frame`,
which runs in a worker thread after the frame has crossed Wi-Fi, waited
in the session's `FrameSlot` and been decoded, so the filter's `dt` is
the capture interval plus the difference of two random delays.

The phone (`capture.js`) calls `performance.now()` after
`canvas.toBlob`, so its stamp also includes JPEG encode time. The
ESP32-CAM (`main.c`) stamps with `esp_timer_get_time()` just before the
send, after `esp_camera_fb_get()`; with `CAMERA_GRAB_LATEST` the frame
it gets may have been sitting in the driver's buffer for part of a frame
period.

`OneEuroFilter.apply` already takes an explicit `t`, used by tests. The
filter, `AimPipeline` and `HoldingPipeline` are shared across sessions
today (fixing that is a separate change, `isolate-cursor-per-session`).

## Goals / Non-Goals

**Goals:**
- The filter's `dt` for a session's frames is the difference of their
  capture timestamps.
- A bad client clock can never produce a zero, negative, or huge `dt`.
- No wire-format change; old clients keep working.

**Non-Goals:**
- Estimating the offset between the two clocks, or one-way latency.
  Only differences within one session are used.
- Per-session filters (see `isolate-cursor-per-session`).
- Changing the dropout-hold window, which stays on the server clock: it
  is about how long the *server* has gone without a solve.

## Decisions

### A per-session `CaptureClock` turns client milliseconds into filter seconds
`stream.CaptureClock.stamp(client_ms) -> float` keeps the previous
client timestamp and the time it returned for it. The first frame of a
session is placed at the server's `time.monotonic()`. Each later frame
is placed at `previous + (client_ms - previous_client_ms) / 1000`.

The step is trusted only when it is finite and in `(0, 1 s]`.
Otherwise the step is the server's own interval since the previous
stamp, clamped to `[1 ms, 1 s]`, and the client timeline resumes from
this frame's timestamp. This is "fall back to server time" without ever
letting the filter see a non-positive `dt` (the filter floors `dt` at
1e-9 s, which with the derivative term produces a speed spike) or a
multi-second one that is really a clock jump.

1 s as the bound: at the phone's 20 fps and the ESP32's configured cap,
consecutive frames are 30–100 ms apart; a gap of a second is already a
stall, and the filter's behaviour at `dt` ≥ 1 s is "take the new
sample" either way, so clamping loses nothing.

Alternative: map the client clock onto the server's with a
minimum-latency offset estimate. Rejected: only differences are needed,
and an offset estimate needs a drift model to stay correct over a long
session, which is complexity for no gain here.

Stamping happens in the processing loop, not the receive loop, because
only processed frames reach the filter; frames the slot drops never
need a time. The fallback's server interval is therefore measured
between processing times, which is only used when the client's clock is
already untrustworthy.

### The frame's time is passed down explicitly, not set on shared state
`HoldingPipeline.process_frame(frame, *, debug, t=None)` and
`AimPipeline.process_frame(frame, *, debug, backend=None)`. When `t` is
given, `HoldingPipeline` asks `inject.stamped(backend, t)` for a view of
its backend whose moves are filtered at `t` (a `SmoothingCursorBackend`
returns `self.at(t)`; any other backend is returned as is), and passes
that view to the pipeline for this one call, and uses it for a
dropout-hold re-send as well. `AimPipeline` stays stateless: the
override is an argument, like `debug`.

Alternative: a settable "current frame time" on the smoothing backend
or a clock callable reading it. Rejected: frames from different
sessions are processed concurrently in the default executor, so a
shared mutable "current time" races.

`SmoothingCursorBackend.move_absolute` without a time keeps using the
filter's clock, so anything that moves without a frame (tests, future
callers) behaves as before.

### The phone stamps at capture and skips repeats
A `requestVideoFrameCallback` loop on the preview element records the
latest presented frame's `metadata.captureTime` (present for camera
tracks in Chromium) or, failing that, `metadata.expectedDisplayTime`;
both are on the `performance.now()` timebase. `captureAndSend` uses that
stamp for the frame it draws, or `performance.now()` taken immediately
before `drawImage` when the browser has no `requestVideoFrameCallback`.
If the stamp equals the last one sent, the tick sends nothing: the
video element is still showing the same camera frame, and sending it
again would only give the server a zero interval to fall back from.

`expectedDisplayTime` is not a capture time, but it is a constant
offset from one for a steady camera pipeline, so differences are right,
and differences are all the server uses.

### The ESP32 stamps with the driver's frame timestamp
`camera_frame_t` gains `captured_ms`. On the board it is
`camera_fb_t.timestamp` (set by the esp32-camera driver from
`esp_timer_get_time()` when the frame is captured), in milliseconds; in
the emulator build the fake camera stamps at grab. `main.c` sends
`frame.captured_ms`. Same clock as before, same wire format, just taken
earlier. Round-trip time on the device still differences against
`esp_timer_get_time()`, so it stays meaningful.

## Risks / Trade-offs

- [The displayed round-trip time grows by the encode time and frame
  age] → That is the honest capture-to-cursor number; it is noted in
  the proposal so a jump in the reading after upgrading is expected.
- [`captureTime` / `expectedDisplayTime` semantics vary by browser] →
  Only differences are used, and the server's fallback handles a
  browser that repeats or jumps.
- [Until `isolate-cursor-per-session` lands, two sessions still share
  one filter, and their timelines are independently anchored] → Two
  simultaneous shooters already fight over the shared filter; this
  change makes that neither better nor meaningfully worse, and the next
  change gives each session its own filter.
- [The fake camera's stamp is taken at grab, not capture] → It is a
  fixture loop; there is no capture to time.
- [Firmware changes cannot be compiled in this environment (no ESP-IDF)]
  → The change touches one struct field and three assignments; the
  host tests do not cover `main/`. Flagged for a device build.

## Migration Plan

None. Old clients keep sending send-time stamps, which the server
treats exactly like capture stamps.
