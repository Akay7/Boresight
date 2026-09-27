# runtime-settings Specification

## Purpose
Lets the aim tuning and the operator's view preferences be adjusted
while the server runs and kept across restarts in a settings file, with
a predictable precedence between command-line flags, environment
variables, that file and the built-in defaults.

## Requirements

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

### Requirement: Current settings can be read over the API
The server SHALL answer `GET /settings` with the tuning values in
effect, the view preferences in effect, each tuning value's allowed
range, which settings are pinned by a flag or environment variable
(naming it), whether the cursor backend supports a relative-motion
scale, and the settings file path. Like every endpoint, it SHALL
require the token when one is configured.

#### Scenario: Reading settings reports ranges and pins
- **WHEN** the server was started with `BORESIGHT_AIM_BETA=3.0` and a
  client reads the settings
- **THEN** the response carries a beta of 3.0, the allowed range for
  every tuning value, and marks beta as pinned by `BORESIGHT_AIM_BETA`

#### Scenario: Settings are not readable without the token
- **WHEN** a token is configured and a client reads the settings
  without presenting it
- **THEN** the request is refused

### Requirement: Tuning can be changed while the server runs
The server SHALL accept a change to any subset of the tuning values on
`POST /settings/tuning` and SHALL validate each against its allowed
range on the server, refusing the whole request, and changing nothing,
if any value is not a number or is outside its range. An accepted
change SHALL take effect without a restart or reconnect: for every
session, including those already streaming, from its next processed
frame, and for the relative-motion scale, from the next cursor move.
Changes arriving concurrently SHALL each be applied whole, never
interleaved field by field. The response SHALL carry the settings now
in effect. The allowed ranges SHALL be: `min_cutoff` 0.01–10 Hz,
`beta` 0–10, `hold_s` 0–5 seconds, `rel_scale` 0–10000.

#### Scenario: A running session picks up a new filter parameter
- **WHEN** a session is streaming and a client changes `min_cutoff`
- **THEN** the session's next processed frame is smoothed with the new
  value, the session's existing smoothing state is kept, and its
  connection is not interrupted

#### Scenario: A partial change leaves the rest alone
- **WHEN** a client posts only a new `hold_s`
- **THEN** `hold_s` changes and every other tuning value keeps its
  value

#### Scenario: An out-of-range value is rejected
- **WHEN** a client posts `beta = 50`
- **THEN** the request is refused as invalid and no tuning value
  changes

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

### Requirement: Persisted view preferences are restored at startup
At startup the server SHALL apply the saved view preferences: new
sessions SHALL inherit the saved debug overlay setting, the overlay
margin SHALL be the saved one, and where the saved marker source is
on-screen, the server SHALL select on-screen markers without delaying
startup. A selection that fails SHALL leave printed markers active and
be logged, exactly as a failed selection from a client would.

#### Scenario: On-screen markers come back after a restart
- **WHEN** the file saves `view.marker_source = "screen"` and the
  server starts where the overlay can run
- **THEN** on-screen markers become active without any client selecting
  them

#### Scenario: A restore that fails leaves printed markers
- **WHEN** the file saves `view.marker_source = "screen"` and the
  overlay cannot start
- **THEN** the server keeps serving with printed markers active and the
  failure is logged

### Requirement: The display is a view preference that can change live
The view preferences SHALL include `display`, the chosen display's name
(empty for the primary display), settable in the file, with `--display`,
and over the API. `GET /displays` SHALL list the machine's displays with
each one's name, desktop rectangle and whether it is primary, and the
one in effect. `POST /display` SHALL apply a display to the cursor and
the overlay without a restart; a display that cannot be applied SHALL be
refused with a reason and change nothing. A display named in the file or
flag that cannot be applied at startup SHALL stop the server with that
reason. The chosen display SHALL be saved with the other view
preferences.

#### Scenario: Listing displays
- **WHEN** a client requests `GET /displays` on a machine with two
  monitors
- **THEN** both are listed with name, rectangle and primary flag, and
  the one in effect is named

#### Scenario: Changing the display live
- **WHEN** a client posts a listed display name to `/display`
- **THEN** the cursor and any on-screen markers move to that display and
  the response names it as in effect

#### Scenario: The choice is saved
- **WHEN** a client changes the display and saves settings
- **THEN** the file's `view.display` holds that name
