## 1. Server: session identity

- [x] 1.1 Add `client_kind`, `client_version` and `frame_size` (default
      `None`) to `SessionStats` in `stream.py`; verify existing
      `as_message` tests still pass unchanged (`uv run pytest`)
- [x] 1.2 Handle `{"type": "hello", "client": str, "version"?: str,
      "frame_size"?: [int, int]}` in `server.py`'s `_handle_control`,
      ignoring wrong types; verify with websocket tests: a valid hello
      sets the identity, a hello with a non-string client leaves the
      session unidentified and later frames still solve
- [x] 1.3 Replace the hardcoded "phone connected/disconnected" log
      wording and `client="phone"` default with a client-neutral label
      that includes the kind once known; verify with a `caplog` test that
      an `esp32-cam` session's disconnect line names the kind

## 2. Server: session listing

- [x] 2.1 Add a session registry on `app.state`, registering in
      `stream_frames` after `accept()` and removing in the session's
      `finally`; verify a unit test that the registry is empty after a
      client disconnects, including abruptly
- [x] 2.2 Add `GET /sessions` returning remote address, identity,
      `connected_s` and the stats message without the `debug` key;
      verify tests: a streaming session is listed with its counts and
      `round_trip_ms`, a closed one is absent, a debug-enabled session's
      entry has no `debug` key
- [x] 2.3 Verify with a test that `GET /sessions` returns 401 without the
      token when one is configured and 200 with it

## 3. Server: headless connection details

- [x] 3.1 Add `certificate_fingerprint(certfile)` to `netaccess.py`
      (SHA-256 over DER, colon-separated uppercase hex); verify a test
      that it matches `cryptography`'s fingerprint of a generated
      certificate and is identical across two `resolve_certificate`
      calls
- [x] 3.2 Print a device block in `server.main()` after the phone URL:
      host, port, frame socket path, TLS on/off, token, and under TLS the
      certificate path and fingerprint; verify with a `capsys` test
      calling `main()` with `uvicorn.run` patched, for both TLS and
      plain-text configurations

## 4. Phone client hello

- [ ] 4.1 In `web/capture.js`, send `{"type": "hello", "client": "phone",
      "frame_size": [w, h]}` from the socket's `open` handler on every
      connection; verify manually in a desktop browser against a local
      server that `GET /sessions` lists the session as `phone`, and
      again after reloading the page

## 5. Verification

- [x] 5.1 Run `uv run pytest` and `uv run pre-commit run --all-files`;
      verify both pass
