## 1. Server

- [x] 1.1 Add `shot.py` with `AimHistory` (record, trim to 1000 ms / 64 entries, clear on a backwards timestamp, `covers`, `aim_at` nearest solved within 100 ms) and `TriggerQueue` (ordered actions, head-only readiness, forced drain); verify with `tests/test_shot.py`
- [x] 1.2 Parse `frame_ms` in `_handle_control` into a `TriggerAction` (finite numbers only), queue it, and drain between frames, on arrival when idle, and on a 250 ms deadline; move the raw backend to the shot's aim before a press that actually presses; verify with e2e tests in `tests/test_stream_e2e.py`: shot lands at the frame's unsmoothed aim while the smoothed cursor trails, a waiting `down`+`up` keeps order, an unsolved frame fires in place, a never-arriving frame still fires, legacy triggers unchanged, no move while held

## 2. Clients

- [x] 2.1 Send `frame_ms` (the last sent frame's stamp) with `down` in `capture.js`, omitted before any frame; verify `node --check` and, on a phone, that shots land at the aim during a swing (`node --check` done; the on-phone check is still pending)
- [x] 2.2 Add `bp_format_trigger_down(frame_ms)` to `boresight_proto` with a host test, record the last sent frame per connection in `link.c`, add `link_send_trigger_down()` and use it from `buttons.c`; verify the host tests build and pass, device build pending ESP-IDF

## 3. Wrap-up

- [x] 3.1 Document shot-at-frame-aim in README's trigger section and the wire protocol; run `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check` and `openspec validate fire-trigger-at-frame-aim --strict`
