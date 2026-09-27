## Why

Settings live in three places: the settings file holds the aim tuning
and view preferences, while the network, TLS, marker layout, detection
and recording options exist only as command-line flags, and the
detection thresholds exist only as module constants. A setup has to be
retyped on every start, and there is no single place to see how a
server is configured.

## What Changes

- The settings file gains `[server]` (`host`, `port`, `token`,
  `token_auto`, `tls`, `certfile`, `keyfile`, `qr`), `[markers]`
  (`layout`), `[detection]` (`tracked`, `coarse_min_side_px`,
  `full_pass_every`, `backoff_frames`) and `[recording]` (`seconds`,
  `max_mb`) tables, validated like the existing ones.
- Every existing command-line flag becomes an override of its file key,
  with the same precedence as the tuning flags (flag > environment
  variable > file > default). Boolean flags gain a negative form
  (`--no-tls`, `--qr`, `--no-token-auto`, `--tracked-detection`) so a
  flag can override the file either way.
- The tracker's thresholds, previously constants, are read from
  `[detection]` and handed to each session's tracker.
- Saving from the phone still writes only `[tuning]` and `[view]`; the
  new tables are edited by hand and preserved on save.
- Calibration results (`lenses.json`, `zeroing.json`) stay in their own
  files: they are measurements the server writes, not settings.

## Capabilities

### New Capabilities

### Modified Capabilities
- `runtime-settings`: the file holds every server option, not only the
  tuning and view tables, and each follows the fixed precedence.

## Impact

- `src/boresight/settings.py` (models, CLI key map), `server.py`
  (`main()` reads settings, flags become overrides), `pipeline.py` /
  `detect.py` / `marker_source.py` (tracker options instead of a
  boolean), `README.md` settings section, tests.
- No change for a user who passes flags as today; a user can now move
  them into `.boresight/config.toml`.
