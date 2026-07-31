## 1. Frame transport

- [x] 1.1 Add `src/boresight/stream.py` with the frame message codec:
      pack/unpack an 8-byte little-endian float64 timestamp prefix
      followed by JPEG bytes, rejecting messages shorter than the header
- [x] 1.2 Add a `FrameSlot` single-slot mailbox that overwrites on put,
      counts the overwrite as a drop, and lets a consumer await the
      newest frame
- [x] 1.3 Add a `SessionStats` record tracking received, processed,
      dropped and failed counts plus decode/solve timings and the last
      round-trip time, with a helper asserting the counts reconcile
- [x] 1.4 Add `tests/test_stream_codec.py` covering the codec round
      trip, the short-message rejection, and the slot's newest-wins and
      drop-counting behaviour

## 2. WebSocket endpoint

- [x] 2.1 Add the frame WebSocket route to `server.py`, running a
      receive task that only fills the slot and never decodes
- [x] 2.2 Add the processing task: take the newest frame, run
      `cv2.imdecode` and `pipeline.process_frame` in a thread executor,
      and count a decode failure as a failed frame without closing the
      connection
- [x] 2.3 Push a JSON telemetry message back to the client on an
      interval, carrying the counts, timings, round-trip time, and the
      last solve's marker count and conditioning
- [x] 2.4 Handle disconnect: cancel both tasks, emit no further cursor
      movement for that connection, and start the next connection's
      counters from zero
- [x] 2.5 Extend `create_app` to build a `MarkerMap` and an
      `AimPipeline` at startup through the same injection seam as the
      cursor backend, so tests substitute both without a device

## 3. Network access

- [x] 3.1 Add configuration for bind host, port, token, and TLS
      certificate paths, defaulting to loopback with no token
- [x] 3.2 Add token enforcement as a single layer — HTTP middleware plus
      an explicit pre-accept check on the socket — using
      `secrets.compare_digest`, accepting the token as a query parameter
      or bearer header
- [x] 3.3 Refuse to start when bound to a non-loopback address with no
      token, exiting with an error that names the reason
- [x] 3.4 Generate a self-signed certificate via `cryptography` when TLS
      is requested and none is supplied, persist it, and reuse it on
      later starts
- [x] 3.5 Print the full phone-facing URL at startup, including scheme,
      reachable address, port and token
- [x] 3.6 Add `cryptography` to `pyproject.toml` dependencies

## 4. Phone client

- [x] 4.1 Add `src/boresight/web/index.html`: video preview, connection
      and capture status, a telemetry readout, and a start control
- [x] 4.2 Add `src/boresight/web/capture.js`: request the
      environment-facing camera at the configured resolution, and display
      the resolution and facing mode actually granted
- [x] 4.3 Attempt to pin exposure through the track's constraints and
      report plainly whether the device accepted it
- [x] 4.4 Capture to a canvas at a target rate, encode JPEG at a
      configured quality, prefix the capture timestamp, and send as one
      binary message
- [x] 4.5 Skip a capture when the socket's `bufferedAmount` exceeds the
      threshold, and count the skip rather than queueing
- [x] 4.6 Display incoming telemetry, and display capture or connection
      failures rather than failing silently
- [x] 4.7 Detect an insecure origin (absent `navigator.mediaDevices`)
      and explain it, naming the TLS and `adb reverse` paths
- [x] 4.8 Mount the client with
      `StaticFiles(directory=Path(__file__).parent / "web", html=True)`,
      and derive the socket URL and token in the page from its own
      location rather than a hardcoded host
- [x] 4.9 Verify the client files land in a built wheel
      (`uv build`, then inspect the archive) — the wheel target is
      `src/boresight`, so files outside it are silently omitted and the
      omission is invisible to a suite that runs from a checkout

## 5. Tests

- [x] 5.1 Add `tests/test_stream_e2e.py` streaming the
      `synthetic_video` fixture JPEGs over the socket, synchronised
      frame by frame, and asserting the recorded cursor track equals
      `pipeline.replay()`'s track for the same directory
- [x] 5.2 Assert an unsolvable frame (a `close_range` zero-marker JPEG)
      moves nothing and leaves the connection open
- [x] 5.3 Assert a corrupt payload and an under-length message are each
      counted as failed and do not close the connection
- [x] 5.4 Test the drop policy directly by holding the processor while
      pushing frames past it, asserting only the newest is processed and
      the drop count matches
- [x] 5.5 Assert telemetry arrives with counts that reconcile, and that
      a second connection starts from zero
- [x] 5.6 Add `tests/test_network_access.py`: unauthenticated HTTP
      rejected, unauthenticated socket closed with a policy status,
      valid token served normally, and no-token loopback unaffected
- [x] 5.7 Assert the token layer covers the static client mount, not
      only the routes — middleware runs ahead of a mounted
      sub-application, and a route-level dependency would not have
- [x] 5.8 Assert startup refuses a non-loopback bind without a token,
      and that a generated certificate is reused rather than regenerated

## 6. Documentation and gate

- [x] 6.1 Update README's "Running the server" section: bind address,
      token, TLS, the generated URL, and both phone paths (self-signed
      TLS and `adb reverse`)
- [x] 6.2 Document the secure-context requirement prominently — it is
      the first thing that will stop someone, and the symptom (no camera
      API at all) does not suggest its cause
- [x] 6.3 Document the wire protocol, the drop policy and the telemetry,
      and state that no latency figure has been measured yet
- [x] 6.4 Tick the "Web server: phone connects over Wi-Fi" milestone and
      note that the trigger and filtering are still absent. Correct
      "Repo layout": it sketches `web/` at the repository root, which
      would not ship in the wheel — move it under `src/boresight/` and
      add `stream.py`
- [x] 6.5 Run `uv run pytest`, `uv run ruff check`, `uv run ruff format
      --check` and `uv run pre-commit run --all-files` clean
- [x] 6.6 Run `openspec validate add-phone-video-stream --strict`
