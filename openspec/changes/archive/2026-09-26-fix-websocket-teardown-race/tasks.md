## 1. Reproduce

- [x] 1.1 Loop the affected test files (30 runs) and capture the escaping `CancelledError` traceback with a portal-wrapping pytest plugin; verify by recording the failure count and traceback in design.md

## 2. Cursor gate

- [x] 2.1 Add `_GatedCursor.close()` in `shooter.py` (closes the gate and frees an owned cursor under the arbiter's lock; `move_absolute` drops moves once closed); verify with new `tests/test_shooter.py` tests
- [x] 2.2 Call `cursor.close()` in `run_frame_session`'s teardown in place of `arbiter.release(stats)`, still before the first `await`; verify `tests/test_cursor_ownership.py` passes

## 3. Teardown

- [x] 3.1 Shield the executor job in `process_loop` and keep it as `in_flight`, with a done-callback that retrieves its exception; verify the existing stream tests pass
- [x] 3.2 Replace the final `gather` with `asyncio.wait` over the pending tasks and the in-flight job, then retrieve finished tasks' exceptions; verify a new test that cancels the teardown sees the canceller's own `CancelledError`
- [x] 3.3 Add an end-to-end test where a frame is still in the executor at disconnect and must not move the cursor; verify it fails before 2.x and passes after

## 4. Evidence

- [x] 4.1 Run the affected files at least 50 times and the full suite 5 times with 0 failures; verify by recording the numbers in design.md
- [x] 4.2 `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check` and `openspec validate fix-websocket-teardown-race --strict` pass
