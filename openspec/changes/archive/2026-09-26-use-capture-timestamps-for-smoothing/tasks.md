## 1. Server timing

- [x] 1.1 Add `CaptureClock` to `stream.py` (first frame at server time, client deltas when finite and in (0, 1 s], otherwise the server interval clamped to [1 ms, 1 s]); verify with `tests/test_capture_clock.py` covering steady deltas, jitter-free timing, repeats, backwards and forward jumps, NaN, and recovery after a jump
- [x] 1.2 Add `SmoothingCursorBackend.at(t)` and `inject.stamped()`, so a move can be filtered at an explicit time; verify in `tests/test_inject.py` that stamped moves use the given `dt` and unstamped moves still use the clock
- [x] 1.3 Let `AimPipeline.process_frame` take a per-call `backend`, and `HoldingPipeline.process_frame` a `t` that stamps both solved moves and hold re-sends; verify in `tests/test_aim_hold.py`
- [x] 1.4 Stamp each processed frame with the session's `CaptureClock` in `server.run_frame_session` and pass it through `_decode_and_solve`; verify with an e2e test in `tests/test_stream_e2e.py` that the filter sees client-timestamp intervals regardless of arrival timing

## 2. Clients

- [x] 2.1 Stamp phone frames at capture in `capture.js` (`requestVideoFrameCallback` captureTime/expectedDisplayTime, else `performance.now()` before `drawImage`) and skip a tick whose stamp equals the last sent; verify manually on a phone that frames still stream and the RTT reading includes encode time (done here: `node --check`; the on-phone check is still pending)
- [x] 2.2 Carry the driver's capture time in `camera_frame_t.captured_ms` (`camera.c`, `camera_fake.c`) and send it from `main.c`; verify the host tests still build and pass (`cmake -S test_host -B build-host && cmake --build build-host && ctest --test-dir build-host`), device build pending hardware/ESP-IDF

## 3. Wrap-up

- [x] 3.1 Document capture-time smoothing in README where smoothing and the wire format are described; run `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check` and `openspec validate use-capture-timestamps-for-smoothing --strict`
