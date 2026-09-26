## 1. Buffer and writer

- [ ] 1.1 Add `src/boresight/recording.py` with `RecordingConfig`
      (seconds, max bytes, root directory) and `FrameRecorder`: a deque
      of frame entries evicted by age and by retained bytes, `frame()`,
      `result()`, `control()` (trigger and hello fields only), and a
      snapshot; verify with unit tests in `tests/test_recording.py`
      covering window eviction, byte-cap eviction, result annotation and
      that raw control text is never retained
- [ ] 1.2 Add `save_recording()` writing `frame_NNNN.jpg`, `markers.toml`
      (via `markers.layout_toml`) and a fixture-compatible
      `manifest.json` into a new timestamped directory under
      `.boresight/recordings/`, omitting frames solved against a layout
      other than the newest's; verify with tests that the files are byte
      for byte the payloads, the manifest has the fixture keys, and two
      saves in one second get distinct directories
- [ ] 1.3 Add a read-only `marker_map` property to `AimPipeline`; verify
      it returns the map the pipeline was built with

## 2. Server wiring

- [ ] 2.1 Give each frame session a recorder when recording is enabled:
      record each unpacked frame with the current layout, each processed
      frame's outcome and position, and each control message; none of
      this when disabled; verify via the socket tests below
- [ ] 2.2 Handle `{"type": "record"}` on the frame socket: save on a worker
      thread and answer `{"type": "recording", "path", "frames"}` or
      `{"type": "recording", "error"}`; verify with a socket test
- [ ] 2.3 Add `POST /recordings` saving every live session's buffer, behind
      the existing token middleware; verify it saves a streaming session
      and returns 401 without the token
- [ ] 2.4 Add `--record-seconds` (default 10, 0 disables) and
      `--record-max-mb` (default 64) to `python -m boresight.server`,
      passed to `create_app`; verify `--help` lists them and a disabled
      server answers a record message with an error

## 3. Replay

- [ ] 3.1 Make `python -m boresight.pipeline <dir>` default to
      `<dir>/markers.toml` when present and `--config` is not given;
      verify with a CLI test on a saved recording
- [ ] 3.2 Add the round-trip test: stream the synthetic-video fixture over
      the socket, save a recording, replay it with its own layout, and
      assert the track equals the replay of the original fixture frames;
      also run `test_solve_video_e2e`-style detect+solve over it from
      the manifest keys alone
- [ ] 3.3 Test that no file in a recording made under a token-protected
      server contains the token

## 4. Phone client

- [ ] 4.1 Add a "Save last N s" button to `index.html`, enabled while
      streaming, that sends `{"type": "record"}` from `capture.js` and
      shows the returned path and frame count (or error) in the message
      area; verify by a served-page test that the button and handler are
      present
- [ ] 4.2 On a real phone: stream, press save, confirm the message shows
      the path and that `python -m boresight.pipeline <path> --dry-run`
      replays it — needs hardware

## 5. Docs and checks

- [ ] 5.1 Add a short README section on saving and replaying a recording
- [ ] 5.2 Run `uv run ruff check`, `uv run ruff format --check`,
      `uv run pytest -q` and `openspec validate --all --strict`; all pass
