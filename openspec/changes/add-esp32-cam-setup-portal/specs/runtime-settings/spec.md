## MODIFIED Requirements

### Requirement: Settings are read from a settings file
The server SHALL read its settings from a TOML settings file, at
`.boresight/config.toml` relative to the working directory unless
another path is given with `--config`. The file SHALL be able to hold
every setting the server takes: a `server` table (`host`, `port`,
`token`, `token_auto`, `tls`, `certfile`, `keyfile`, `qr`, `announce`),
a `markers` table (`layout`), a `detection` table (`tracked`,
`coarse_min_side_px`, `full_pass_every`, `backoff_frames`), a
`recording` table (`seconds`, `max_mb`), a `tuning` table
(`min_cutoff`, `beta`, `hold_s`, `rel_scale`) and a `view` table
(`debug`, `marker_source`, `overlay_extra_margin_px`). Any key it omits
takes its built-in default, and a missing file is the same as an empty
one. Top-level tables the server does not know SHALL be ignored, so
other state can share the file. A file that cannot be parsed, a value
of the wrong type or outside its allowed range, or an unknown key inside
a known table SHALL stop the server at startup with a message naming the
file and the offending value.

#### Scenario: Values in the file take effect
- **WHEN** the settings file sets `tuning.beta = 2.0` and nothing else
  sets it
- **THEN** every session's aim filter uses a beta of 2.0

#### Scenario: Server options come from the file
- **WHEN** the settings file sets `server.port = 9100`,
  `server.tls = true` and `recording.seconds = 5`, and no flag sets them
- **THEN** the server listens on port 9100 over TLS and keeps 5 seconds
  of each session's frames

#### Scenario: Detection thresholds come from the file
- **WHEN** the settings file sets `detection.coarse_min_side_px = 48`
- **THEN** every session's tracker searches a half-size frame only while
  its markers are at least 48 pixels across

#### Scenario: A missing file means defaults
- **WHEN** no settings file exists at the configured path
- **THEN** the server starts with every setting at its built-in default

#### Scenario: An out-of-range value refuses to start
- **WHEN** the settings file sets `tuning.min_cutoff = -1`
- **THEN** the server exits at startup with an error naming the file
  and `min_cutoff`, and serves nothing

#### Scenario: Announcing is switched off from the file
- **WHEN** the settings file sets `server.announce = false` and no flag
  sets it
- **THEN** the server starts without announcing itself on the local
  network
