## Why

Aim feel is tuned by feel — the One-Euro filter's `min_cutoff` and
`beta`, the dropout hold window, and the relative-motion scale depend on
the camera, the lighting and the game — yet the only way to change them
today is an environment variable read once at startup (or, for the hold
window, a code constant). Every adjustment costs a server restart and a
reconnect, which is exactly the wrong loop for something judged by
aiming at the screen. The phone-side preferences the server does keep
(the debug overlay default, the marker source, the overlay margin) live
only in memory and are lost on every restart.

## What Changes

- A settings file, `.boresight/config.toml` by default and chosen with
  `--config`, holding a typed, range-checked settings model: a `[tuning]`
  table (`min_cutoff`, `beta`, `hold_s`, `rel_scale`) and a `[view]`
  table (`debug`, `marker_source`, `overlay_extra_margin_px`). Each value
  is resolved with the precedence CLI flag > environment variable >
  settings file > built-in default. New CLI flags `--aim-min-cutoff`,
  `--aim-beta`, `--aim-hold-s`, `--rel-scale`; new env var
  `BORESIGHT_AIM_HOLD_S` alongside the existing
  `BORESIGHT_AIM_MIN_CUTOFF`, `BORESIGHT_AIM_BETA`, `BORESIGHT_REL_SCALE`.
- **BREAKING**: an unparseable or out-of-range value in an env var, a CLI
  flag or the settings file now stops the server at startup with a
  message naming it, instead of silently falling back to the default.
- Authenticated endpoints: `GET /settings` (current values, their
  allowed ranges, which are pinned by a flag or env var, and the file
  path), `POST /settings/tuning` (partial update, validated server-side,
  applied live) and `POST /settings/save` (write the file atomically).
- A tuning change reaches every session already streaming on its next
  frame — each session's own filter and hold take the new parameters
  without being reset — and the relative-motion scale reaches the cursor
  backend immediately. No restart, no reconnect.
- The view preferences are restored at startup: the debug overlay
  default, the overlay margin, and the marker source (on-screen markers
  are re-selected in the background; a failure leaves printed markers
  active, as a failed selection always does).
- A tuning panel on the phone: sliders for min cutoff, beta, hold time
  and relative scale, and a Save button that persists everything
  currently in effect.

## Capabilities

### New Capabilities
- `runtime-settings`: the settings file and its precedence, the
  read/update/save API, live application to running sessions, and
  restoring persisted preferences at startup.

### Modified Capabilities
- `aim-hold`: the hold window is a configurable, live-adjustable
  setting rather than a fixed constant.
- `aim-smoothing`: the filter's parameters can change while a session
  streams, without resetting its smoothing state.
- `phone-client`: a tuning panel with sliders and a save control.

## Impact

- New `src/boresight/settings.py` (model, precedence, TOML read/write,
  live store) and `src/boresight/settings_routes.py` (endpoints).
- `one_euro.py`, `aim_hold.py`, `inject.py`, `marker_source.py`: small
  setters so parameters can change in place; env-var parsing moves out
  of `inject.py` and `marker_source.py` into `settings.py`.
- `server.py`: new CLI flags and `--config`, settings wiring in
  `create_app` and its lifespan, router include.
- `web/index.html`, `web/capture.js`: one new panel, self-contained.
- No new dependencies: `tomllib` reads TOML; the file is written by a
  small serializer for the flat tables it holds.
- `.boresight/` already exists (certificates) and is git-ignored; the
  settings module keeps its file helpers generic so other per-machine
  state can live alongside.
