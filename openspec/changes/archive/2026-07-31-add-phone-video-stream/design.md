## Context

`pipeline.py` takes a numpy array and moves the cursor. Everything
upstream of that array is missing. This change supplies it from a phone
over Wi-Fi.

Three existing facts shape the design:

- The rendered fixtures are **JPEG**, chosen because "that is what the
  phone will actually stream". If the wire format is JPEG, the fixture
  files are wire-format bytes and can be sent down a socket verbatim.
  The end-to-end test writes itself.
- `pipeline.process_frame` is stateless and synchronous. It is a
  blocking CPU call, which in an async server is the entire design
  problem.
- README has been deferring a security question, in its own words: the
  phone path "needs both a LAN-reachable bind address and a real auth
  story before it's safe to open up". This is the change that opens it.

## Goals / Non-Goals

**Goals:**

- A phone in a browser, aimed at the TV, moves the PC's cursor.
- Streaming a fixture over the socket produces byte-identical cursor
  output to replaying it from disk — the transport adds nothing.
- Round-trip time is measurable from the phone, on day one, without
  external tooling.
- Exposing the server to the network without authentication is not a
  configuration the software will accept.

**Non-Goals:**

- The trigger button and click injection. The protocol reserves text
  messages for it; the milestone is separate.
- 1-euro filtering. Still the next thing after this.
- WebRTC. README's own condition is "if `getUserMedia`-over-WebSocket
  latency proves too high" — which requires first measuring it, which
  requires this change.
- Camera calibration, `cornerSubPix`, `undistortPoints`, `solvePnP`.
- Multi-gun. Connections are already independent; nothing here
  prevents it, and nothing here implements it.
- Any real latency claim. This change builds the instrument. Reading it
  is a separate exercise on real hardware.

## Decisions

### Wire format: JPEG per binary message, 8-byte timestamp prefix

`[float64 LE client_ms][JPEG bytes...]`, one frame per binary WebSocket
message. Text messages carry JSON control and telemetry.

*Why JPEG over a video codec:* `MediaRecorder` produces a chunked
WebM/VP8 stream whose chunk boundaries do not align to frames, so the
server would have to demux and decode a running stream to recover the
per-frame images the pipeline needs. Bandwidth would be several times
better; frame-boundary clarity would be gone, and so would the ability
to feed fixture files down the socket. WebCodecs `VideoEncoder` is the
right long-term answer and has uneven mobile support today.

*Why the timestamp is in the binary frame rather than a paired text
message:* two messages per frame can interleave under load, and
round-trip time attributed to the wrong frame is worse than none.

*Why a prefix rather than JPEG APP markers:* eight bytes and a
`struct.unpack` against parsing an EXIF segment.

### Concurrency: receiver task, processor task, one-slot mailbox

The receive loop never blocks on processing. It decodes nothing; it
drops the raw message into a single-slot holder, overwriting whatever
is there, and counts the overwrite as a drop. A separate task takes
whatever is in the slot and runs decode + `process_frame` in a thread
executor, because both are blocking CPU work that would otherwise stall
the event loop for the whole server.

*Why newest-wins rather than a queue:* a queue converts a throughput
shortfall into unbounded, monotonically growing latency. Ten seconds
into a session the cursor is following where the player aimed a second
ago, and it never recovers. Dropping costs nothing, because the next
frame carries a strictly better answer than the one discarded.

*Why not apply backpressure to the client instead:* the client is on
Wi-Fi and its send buffer is not a good place to store the backlog
either. Both ends drop; the client checks `bufferedAmount` before
capturing.

*Why a thread executor rather than a process pool:* the work is OpenCV,
which releases the GIL for detection, and the pipeline is a few
milliseconds. Process transfer of a 1280x720 array would cost more than
it saves.

### Auth: a shared token, required on everything, enforced at one layer

A single random token, supplied by configuration or generated at
startup, checked with `secrets.compare_digest`. Enforced in one place
(middleware for HTTP, an explicit check before accepting the socket)
rather than per route, so a route added later is protected by default
rather than by remembering.

*Why not per-device credentials or a real session system:* the threat
is "someone else on your Wi-Fi", the deployment is one person's living
room, and the asset is a mouse cursor. A shared secret is proportionate.
Anything more would be unbuilt security theatre in a project that
currently has none at all.

*Why the token appears in the URL:* a browser cannot set headers on a
WebSocket handshake, and the phone has to receive the token somehow
before it can present it. It arrives as a query parameter on the URL the
person opens. That means it appears in browser history and in server
logs, which is an accepted cost for a LAN token that can be regenerated
by restarting.

### Refuse to start: non-loopback bind without a token

Not a warning. The process exits.

*Why so blunt:* the failure is silent and severe — an endpoint that
moves the operator's mouse, reachable by anything on the network, with
no symptom locally. Warnings in startup logs are not read. The
convenience being denied is "run an open cursor-mover on the LAN", which
nobody has a legitimate reason to want.

### TLS is mandatory for the LAN path, and `adb reverse` is the escape hatch

**This is the finding that most shapes the change.** Browsers expose
`navigator.mediaDevices` only in a secure context. `localhost` is
exempt; a LAN IP over plain HTTP is not. A phone loading
`http://192.168.1.20:8000` will not find the camera API at all — not a
permission prompt, not an error, the object is simply absent. Without
TLS this milestone does not function.

Two supported paths:

1. **TLS with a generated self-signed certificate** (default). Generated
   once via `cryptography`, persisted, reused across restarts so the
   phone's one-time acceptance of the certificate keeps working. The
   phone shows an interstitial the first time.
2. **`adb reverse tcp:8000 tcp:8000` over USB.** The phone then reaches
   the server as `http://localhost:8000`, which *is* a secure context,
   so no certificate and no interstitial. It also removes the Wi-Fi hop
   entirely, which makes it the better path for measuring anything.

*Why generate rather than require the user to supply one:* requiring
manual `openssl` invocation before the first run guarantees nobody gets
to a working system.

*Why `cryptography` rather than shelling out to `openssl`:* the openssl
binary is not present on Windows by default, and README targets Windows
for the `SendInput` path.

### Testing: fixtures as wire bytes, asserted against `replay()`

The e2e test opens a WebSocket against the app with `TestClient`, sends
each fixture JPEG prefixed with a timestamp, and asserts the recorded
cursor track equals what `pipeline.replay()` produces from the same
directory. Verified available with no new dependency:
`TestClient.websocket_connect` works without `wsproto`, since it drives
the ASGI app directly rather than opening a socket.

*Why assert equality against `replay()` rather than against the
manifest:* the manifest comparison is already covered by
`test_pipeline_e2e.py`. What is unproven here is that the transport is
transparent, and the sharpest statement of that is that it changes
nothing. A transport that quietly re-encoded, resized, or reordered
would pass a tolerance-based assertion and fail this one.

*Determinism note:* the drop policy makes the streamed track
non-deterministic under load by design. The test must therefore
synchronise — send a frame, wait for its processing to be acknowledged,
send the next — so it exercises the transport rather than racing the
drop policy. Dropping is tested separately and directly, by holding the
processor and pushing frames past it.

### The client is two static files, not a build step

`index.html` and `capture.js`, served directly. No bundler, no
framework, no `npm`. The client is a canvas, a socket, and a status
readout; a toolchain would be the largest thing in the repository.

### The client lives inside the package, served by `StaticFiles`

`src/boresight/web/`, not a repository-root `web/`, mounted with
`StaticFiles(directory=Path(__file__).parent / "web", html=True)`.

*Why inside the package:* `pyproject.toml` declares
`packages = ["src/boresight"]` for the wheel target. Anything outside
that directory is not installed. A root-level `web/` would work when
running from a checkout — which is how every test and every dev run
would exercise it — and 404 on any installed copy. That is a defect
that hides from the entire test suite, so the layout has to prevent it
rather than a test catch it. README's "Repo layout" sketch shows `web/`
at the root and is wrong on this point.

*Why `StaticFiles` rather than reading the files into routes:*
conditional requests, content types and range handling come free, and
verified above: it needs no `aiofiles` (Starlette dispatches through
`anyio.to_thread`), so it adds no dependency.

*Interaction with auth, verified rather than assumed:* HTTP middleware
runs before a mounted sub-application, so a `StaticFiles` mount is
covered by the token layer like any route. Route-level dependencies
would not have covered it — which is the second reason auth is
middleware rather than a per-route dependency.

## Risks / Trade-offs

**JPEG-over-WebSocket may be too slow, and that is the stated reason to
move to WebRTC** → Accepted deliberately. README's condition for WebRTC
is that this proves too slow, which cannot be evaluated before it
exists. The telemetry in this change is what makes that decision on
evidence rather than assumption.

**Self-signed certificates on Android are a poor experience, and Chrome
has become stricter about them over time** → Mitigated by persisting the
certificate so the acceptance is one-time, and by shipping `adb reverse`
as a fully supported alternative that needs no certificate at all. If
the interstitial path degrades further, `adb reverse` still works.

**The token in a URL leaks into history and logs** → Accepted; stated in
the design rather than hidden. Regenerating is a restart. The
alternative, a login form on a device you are pointing at a television,
is worse.

**Frame dropping makes behaviour load-dependent and hard to reproduce**
→ Mitigated by counting and reporting every drop, and by keeping the
transport tests synchronous so that a real regression cannot hide behind
"it must have dropped that one".

**No real hardware has been tested against, so the resolution, rate,
quality and exposure defaults are guesses** → Accepted and flagged.
They are all configurable, and the telemetry exists precisely to replace
the guesses. Expect the first session on a real phone to change several
of them.

**`create_app` grows in scope** — it now builds a marker map and a
pipeline at startup, not just a cursor backend → Mitigated by keeping
the same dependency-injection seam already used for the backend, so
tests still substitute fakes without a real device or a real camera.
