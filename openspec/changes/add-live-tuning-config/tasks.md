## 1. Tunable collaborators

- [x] 1.1 Add `OneEuroFilter.tune(min_cutoff, beta)` that keeps filter state; verify in `tests/test_one_euro.py` that tuning mid-stream does not move a steady output and later samples use the new cutoff
- [x] 1.2 Make `HoldingPipeline.hold_s` settable; verify in `tests/test_aim_hold.py` that shortening the window stops a hold already under way and zero disables holding
- [x] 1.3 Replace `inject._rel_scale()` with a `rel_scale` constructor argument and settable property on `UinputCursorBackend`; update `tests/test_inject_uinput.py` (env-var tests become property tests)

## 2. Settings model and file

- [x] 2.1 Add `src/boresight/settings.py`: `Tuning`, `ViewPreferences`, `Settings` models with ranges; `resolve_settings(path, env, cli)` with CLI > env > file > default and pinned-key tracking; `SettingsError` naming the source; verify with `tests/test_settings.py` covering each precedence layer, empty env, bad env/file/CLI values, unknown key, unknown table, missing file
- [x] 2.2 Add the TOML serializer and `atomic_write_text` (temp file, fsync, `os.replace`); verify round-trip through `tomllib` and that a failed write leaves the old file
- [x] 2.3 Add `LiveSettings` (snapshot, locked partial update, save with pin-preservation and unknown-table merge); verify with unit tests including concurrent updates applied whole

## 3. Live application

- [x] 3.1 `SessionPipeline` reads the tuning snapshot per frame and applies it to its own filter and hold; `MarkerSourceController` takes an optional `tuning` source and exposes `overlay_extra_margin_px`; remove `_aim_filter`'s env parsing; update `tests/test_marker_source.py` and the `_aim_filter` monkeypatch in `tests/test_stream_e2e.py`
- [x] 3.2 Add `settings_routes.py` (`GET /settings`, `POST /settings/tuning`, `POST /settings/save`), include it in `create_app`, wire `LiveSettings` through the lifespan (debug default, margin, rel scale, background restore of on-screen markers); verify with `tests/test_settings_routes.py`: read, partial update, 422 on out-of-range, live effect on a streaming session, save round-trip, 401 without token, restore of screen source (success and failure)
- [x] 3.3 Add `--config`, `--aim-min-cutoff`, `--aim-beta`, `--aim-hold-s`, `--rel-scale` to `main()`, make `--overlay-extra-margin-px` default to unset, and exit 2 on `SettingsError`; verify with a test calling `main()` with a bad env var

## 4. Phone

- [x] 4.1 Add a tuning panel to `index.html` and a self-contained section to `capture.js`: sliders built from reported ranges, post on change, render the server's reply, pinned marks, rel-scale disabled when unsupported, Save button with outcome message; verify with `node --check src/boresight/web/capture.js` and a test that the served page contains the panel

## 5. Wrap-up

- [x] 5.1 Replace the env-var tuning docs in README.md with a short settings-file section (precedence, keys, ranges, API); run `uv run ruff check`, `uv run ruff format --check`, `uv run pytest -q`, `openspec validate --all --strict`
