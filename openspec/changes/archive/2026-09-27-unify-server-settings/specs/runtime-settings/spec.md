## MODIFIED Requirements

### Requirement: Settings are read from a settings file
The server SHALL read its settings from a TOML settings file, at
`.boresight/config.toml` relative to the working directory unless
another path is given with `--config`. The file SHALL be able to hold
every setting the server takes: a `server` table (`host`, `port`,
`token`, `token_auto`, `tls`, `certfile`, `keyfile`, `qr`), a `markers`
table (`layout`), a `detection` table (`tracked`, `coarse_min_side_px`,
`full_pass_every`, `backoff_frames`), a `recording` table (`seconds`,
`max_mb`), a `tuning` table (`min_cutoff`, `beta`, `hold_s`,
`rel_scale`) and a `view` table (`debug`, `marker_source`,
`overlay_extra_margin_px`). Any key it omits takes its built-in
default, and a missing file is the same as an empty one. Top-level
tables the server does not know SHALL be ignored, so other state can
share the file. A file that cannot be parsed, a value of the wrong type
or outside its allowed range, or an unknown key inside a known table
SHALL stop the server at startup with a message naming the file and the
offending value.

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

### Requirement: Each setting is resolved with a fixed precedence
Each setting SHALL be taken from, in decreasing precedence: its
command-line flag if it has one, its environment variable if it has one
(`BORESIGHT_AIM_MIN_CUTOFF`, `BORESIGHT_AIM_BETA`,
`BORESIGHT_AIM_HOLD_S`, `BORESIGHT_REL_SCALE`), the settings file, then
the built-in default. Every command-line option the server had before
the file held it SHALL remain as a flag overriding its key, and a
boolean setting's flag SHALL have both forms, so the file can be
overridden either way. An environment variable set to an empty string
SHALL count as unset. A flag or environment variable whose value is not
valid for its setting SHALL stop the server at startup with a message
naming it.

#### Scenario: A flag beats an environment variable and the file
- **WHEN** the file sets `tuning.beta = 2.0`, `BORESIGHT_AIM_BETA=3.0`
  is set, and the server is started with `--aim-beta 4.0`
- **THEN** the effective beta is 4.0

#### Scenario: An environment variable beats the file
- **WHEN** the file sets `tuning.beta = 2.0` and `BORESIGHT_AIM_BETA=3.0`
  is set, with no flag
- **THEN** the effective beta is 3.0

#### Scenario: A boolean flag overrides the file either way
- **WHEN** the file sets `server.tls = true` and the server is started
  with `--no-tls`
- **THEN** the server serves plain HTTP

#### Scenario: An unreadable environment variable refuses to start
- **WHEN** `BORESIGHT_REL_SCALE=abc` is set
- **THEN** the server exits at startup with an error naming
  `BORESIGHT_REL_SCALE`

### Requirement: Settings in effect can be saved to the file
On `POST /settings/save` the server SHALL write the tuning values and
view preferences currently in effect to the settings file, creating its
directory if needed, and SHALL replace the file atomically, so a reader
or a crash mid-save sees either the old file or the new one, never a
partial one. A tuning value pinned by a flag or environment variable
and not changed since startup SHALL keep what the file said (or stay
absent), so saving does not copy a temporary override into the file.
Every other table in the file, known or not, SHALL be preserved as the
file had it. The file path SHALL be fixed at startup, never taken from
a request. A failure to write SHALL be reported to the caller and SHALL
leave the previous file intact.

#### Scenario: Saved settings survive a restart
- **WHEN** a client changes `beta` to 2.5, turns the debug overlay on,
  saves, and the server is restarted with no flag or environment
  variable for either
- **THEN** the effective beta is 2.5 and new sessions start with the
  debug overlay on

#### Scenario: An untouched override is not saved
- **WHEN** the server runs with `BORESIGHT_AIM_BETA=3.0`, the file sets
  no beta, and a client saves without changing beta
- **THEN** the saved file still sets no beta

#### Scenario: Unknown tables are preserved
- **WHEN** the settings file holds a table the server does not know and
  a client saves
- **THEN** that table is still in the file afterwards, with the same
  values

#### Scenario: Server tables are preserved
- **WHEN** the settings file holds a `server` table and a client saves
  while a flag overrides one of its values for this run
- **THEN** the table is still in the file afterwards with the file's
  own values

#### Scenario: A failed write keeps the old file
- **WHEN** the new file cannot be written
- **THEN** the save is reported as failed and the previous file is
  unchanged
