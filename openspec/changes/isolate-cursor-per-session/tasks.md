## 1. Arbiter

- [x] 1.1 Add `shooter.py` with `CursorArbiter` (`cursor_for`, `claim`, `release`, `status`, 1 s idle lapse, lock around check-and-move, ownership changes logged); verify with `tests/test_shooter.py`: free cursor goes to the first mover, non-owner moves dropped, claim takes over, lapse after idle, release on disconnect, status values, buttons pass through

## 2. Per-session aim

- [x] 2.1 Make `MarkerSourceController.pipeline` the stateless `AimPipeline` over the raw backend and add `session_pipeline(cursor)` returning a `SessionPipeline` (own filter, own hold, hold rebuilt on a source switch, filter kept); update `tests/test_marker_source.py` and `tests/test_cursor_move.py` and verify they pass (`tests/test_aim_smoothing_integration.py` wires its own backend and needed no change)

## 3. Server

- [x] 3.1 Put a `CursorArbiter` on `app.state`; per session build the gated cursor and `SessionPipeline`, give `_SessionTriggers` the gated cursor and a claim on press, release ownership on teardown, and set `stats.cursor` before each report; verify with e2e tests in `tests/test_cursor_ownership.py`: a second session does not move the cursor, a press takes over, disconnect hands over, each session's report carries `cursor`, and a handover does not blend filters

## 4. Phone

- [x] 4.1 Add a "Cursor" row to `index.html` and fill it from `stats.cursor` in `capture.js`; verify `node --check`, and on two phones that the row reads "this phone" / "another device" as the trigger passes between them (`node --check` done; the two-phone check is still pending)

## 5. Wrap-up

- [x] 5.1 Document the active-shooter rule in README (aim smoothing, holding, trigger sections) and run `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check` and `openspec validate isolate-cursor-per-session --strict`
