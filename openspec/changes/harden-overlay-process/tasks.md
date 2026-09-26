## 1. Draining the overlay's output

- [x] 1.1 Add `_PipeDrain` to `marker_source.py`: a daemon thread per
      pipe that reads length-capped lines until EOF, keeps a bounded
      tail, forwards lines to the `boresight.overlay` logger at DEBUG,
      and hands its first line to a waiter; verify with a unit test
      that the tail is bounded in lines and line length
- [x] 1.2 Start a stderr drain and a stdout drain immediately after
      launch, and read the geometry line from the stdout drain with
      the existing timeout (killing the child on timeout), replacing
      `_readline_with_timeout`; verify the existing handshake and
      timeout tests still pass
- [x] 1.3 Build `_explain_exit` from the stderr tail, with the join
      bounded by `STOP_TIMEOUT_S`; verify the refusal and silent-exit
      tests still pass
- [x] 1.4 Append the overlay's last output line to the error when it
      exits on its own, and log it at WARNING; verify with a test
- [x] 1.5 Test a stub overlay that writes well over 64 KiB to stderr
      before and after its geometry line, and 64 KiB+ to stdout after
      it: selection succeeds, the overlay stays alive and is observed
      to finish writing, within a bounded time
- [x] 1.6 Test a stub that writes 64 KiB+ to stderr and then exits
      with an explanation: the error carries the explanation and is
      bounded in size

## 2. Serializing switches

- [x] 2.1 Add a `threading.Lock` and a `_closed` flag to the
      controller; take the lock in `select()`,
      `set_overlay_extra_margin_px()`, `stop_overlay()` and
      `shutdown()`, with internal helpers that assume it is held
- [x] 2.2 Make setting the margin already in effect a no-op while
      printed or while the overlay is alive; verify with a test that
      the launcher is not called again
- [x] 2.3 Make `state()` try the lock without blocking, reap only when
      it holds it, and report `switching`; verify with a test that a
      read during a slow start returns promptly with `switching: true`
- [x] 2.4 Make `shutdown()` set `_closed`, abort an in-progress start
      by terminating its process, then stop anything left under the
      lock; refuse starts once closed; verify with tests for shutdown
      during a slow start (prompt, no process left) and selection
      after shutdown (nothing launched)
- [x] 2.5 Test concurrent `select(SCREEN)` calls from several threads:
      exactly one launch, every caller sees `screen`, one live process
- [x] 2.6 Test a concurrent `select(SCREEN)` and margin change: every
      launched process except the one the controller holds is dead
- [x] 2.7 Test concurrent `POST /markers/source` requests through the
      FastAPI app: one overlay started

## 3. Verification

- [x] 3.1 Run `uv run pytest -q`, `uv run ruff check` and
      `uv run ruff format --check`, all passing
- [x] 3.2 Run `openspec validate harden-overlay-process`
