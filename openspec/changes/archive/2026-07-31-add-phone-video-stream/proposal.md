## Why

Every piece of the software path now exists and is tested — detection,
the marker map, the solver, and `pipeline.py` joining them to cursor
injection — but it is fed exclusively by frames rendered in Blender
months of project-time before any camera existed. Boresight has never
seen a real photon.

The phone is the camera. Nothing connects it. This change builds that
connection: a page the phone loads in its browser, which captures from
the rear camera and streams frames to the PC, where the existing
pipeline turns them into cursor movement.

It is also the change that first exposes the server to the network, so
it is the change that has to answer the security question README has
been deferring: something that moves your mouse must not be reachable
by anything on the Wi-Fi that asks.

## What Changes

- Add `src/boresight/web/index.html` and `src/boresight/web/capture.js`:
  a phone client that opens the rear camera via `getUserMedia`, draws
  each frame to a canvas, encodes it as JPEG, and sends it over a
  WebSocket. Includes exposure pinning via `MediaTrackConstraints` where
  the device exposes it — README calls this "the single setting that
  determines whether the project works". The files live inside the
  package, not at the repository root, so they ship in the wheel and are
  served by FastAPI from an installed copy rather than only from a
  checkout.
- Add a WebSocket endpoint that receives those frames, decodes them,
  and drives `pipeline.process_frame`, moving the real cursor.
- Define the wire protocol: binary messages are one frame each, an
  8-byte client timestamp followed by JPEG bytes; text messages are
  JSON control and telemetry. The frame format is JPEG because that is
  what the rendered fixtures already are, so fixture bytes can be fed
  down the socket verbatim.
- Add newest-wins frame dropping. A frame that queues behind another is
  a stale aim point, and a stale aim point is worse than a skipped one.
- Add per-connection telemetry — frames received, processed, dropped,
  decode and solve timings, and round-trip time computed from the
  client's own timestamp — pushed back to the phone and displayed on
  it. README is explicit that round-trip time must be measured before
  anything else is tuned.
- Add a LAN bind address, a shared-token auth layer covering every
  endpoint, and TLS. The server SHALL refuse to start bound to a
  non-loopback address without a token, so an unauthenticated
  cursor-mover cannot be exposed by accident.
- **BREAKING**: `POST /cursor/move` now requires the token when one is
  configured. Existing `curl` invocations against a loopback server
  with no token configured keep working unchanged.
- Add tests that replay the checked-in JPEG fixtures through the
  WebSocket endpoint and assert the resulting cursor track is identical
  to the one `pipeline.replay()` produces from the same files.

Explicitly out of scope: the on-screen trigger button and click
injection (its own milestone; the protocol reserves room for it), the
1-euro filter, WebRTC, and camera calibration.

## Capabilities

### New Capabilities
- `video-ingest`: the server side of the camera link — WebSocket
  lifecycle, frame framing and decode, the drop policy, dispatch into
  the pipeline, and the telemetry reported back.
- `phone-client`: the browser page — camera selection and constraints,
  frame capture and encoding, connection handling, and what it shows
  the person holding the gun.
- `network-access`: reaching the server from another device safely —
  bind address, shared-token authentication across every endpoint, the
  refusal to expose an unauthenticated server, and the secure-context
  requirement that `getUserMedia` imposes.

### Modified Capabilities
- `cursor-injection`: the move endpoint is unchanged in behaviour but
  now sits behind the token layer when one is configured, so its
  requirement must say so rather than describing an endpoint any client
  can call.

## Impact

- New: `src/boresight/web/{index.html,capture.js}`,
  `src/boresight/stream.py`, and their tests.
- Modified: `src/boresight/server.py` — mounts the client, adds the
  WebSocket route, applies auth, and gains bind/TLS/token options. Its
  `create_app` seam grows a marker-map argument so the pipeline can be
  built at startup.
- Packaging: `pyproject.toml`'s wheel target is `src/boresight`, so the
  client files must live inside it. A repository-root `web/` would work
  from a checkout and 404 from an installed wheel — README's "Repo
  layout" sketch shows it at the root and needs correcting.
- Unchanged: `pipeline.py`, `solve.py`, `detect.py`, `marker_map.py`,
  `inject.py`, `markers.py`. This change is a new frame source for an
  existing pipeline, not a change to it.
- Fixtures: reused as WebSocket input, not regenerated. No fixture byte
  changes.
- Dependencies: `cryptography`, for generating the self-signed
  certificate. Verified as the only addition — `uvicorn[standard]`
  already brings `websockets` for the runtime socket, and Starlette's
  `TestClient` speaks WebSocket without one, so the tests need nothing
  new. Shelling out to the `openssl` binary would avoid the dependency
  but would not survive the eventual Windows path, where it is not
  present by default.
- Deployment: **`getUserMedia` requires a secure context.** A phone
  loading `http://192.168.x.x:8000` will find `navigator.mediaDevices`
  undefined — plain HTTP over a LAN IP cannot access the camera in any
  current mobile browser. This change must ship a working answer (TLS
  with a generated self-signed certificate, plus `adb reverse` over USB
  as the zero-configuration alternative) or the milestone does not
  function at all.
- README: "Running the server (current slice)", the Milestones list,
  and "Repo layout" all describe the phone path as future work.
