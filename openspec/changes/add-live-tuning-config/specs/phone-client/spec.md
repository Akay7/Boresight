## ADDED Requirements

### Requirement: The client can tune aim and save settings
The client SHALL offer a tuning panel with a slider for each tuning
value — smoothing minimum cutoff, smoothing beta, hold time and
relative-motion scale — bounded by the ranges the server reports, and
showing each value currently in effect. Releasing a slider SHALL send
the new value to the server, which applies it live; the client SHALL
show what the server reports back rather than what was requested, and
SHALL show the server's reason if a change is refused. A value pinned
by a flag or environment variable SHALL be marked as such. A save
control SHALL ask the server to persist the settings in effect and
SHALL report whether it succeeded. The panel belongs on the phone for
the same reason the marker controls do: tuning is judged by aiming at
the display, which is where the person holding the phone is.

#### Scenario: A slider change takes effect without reconnecting
- **WHEN** the person moves the beta slider while streaming
- **THEN** the new value is sent, the displayed value is the one the
  server reports, and the video connection is not restarted

#### Scenario: Saving reports the outcome
- **WHEN** the person presses save
- **THEN** the client shows that the settings were saved, or the
  server's reason they were not

#### Scenario: A pinned value says so
- **WHEN** the server reports a tuning value as pinned by an
  environment variable
- **THEN** the panel marks that value as set by that variable, so a
  saved change is not expected to survive a restart
