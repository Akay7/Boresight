## ADDED Requirements

### Requirement: Sessions apply their stored lens calibration
The server SHALL, for each processed frame, look up the stored lens
calibration matching the session's client kind, its camera label and
the decoded frame's pixel size, and SHALL pass it to the per-frame
operation. When no calibration matches, the frame SHALL be processed
exactly as before, with no lens model. A session's telemetry SHALL
carry the RMS error of the calibration applied to its latest frame,
and SHALL omit that field entirely when none was applied.

#### Scenario: An uncalibrated session is unchanged
- **WHEN** a session streams and no calibration matches it
- **THEN** its frames are processed without a lens model and its
  telemetry carries no lens field

#### Scenario: A calibrated session is corrected
- **WHEN** a stored calibration matches a session's client kind, camera
  label and frame size
- **THEN** its frames are processed with that lens model, and its
  telemetry reports the calibration's RMS error

### Requirement: Hello may name the camera
The `hello` control message SHALL accept an optional `camera` string
naming which camera is streaming, bounded in length like the other
`hello` fields. It SHALL be part of the session's calibration key. A
missing or non-string camera SHALL leave the session without a camera
label and SHALL NOT invalidate the rest of the `hello`.

#### Scenario: Camera label is recorded
- **WHEN** a client sends `hello` with client kind `phone` and a camera
  label
- **THEN** the session's calibration key includes that label

#### Scenario: A non-string camera is ignored
- **WHEN** a client sends `hello` with a numeric `camera`
- **THEN** the session is identified by its client kind with no camera
  label

### Requirement: Calibration progress is reported in telemetry
While a calibration has been started in a session, and after it
finishes, that session's telemetry SHALL carry its calibration status:
whether it is capturing, done, failed or cancelled, how many views have
been kept out of how many are needed, and, once computed, the RMS
reprojection error. A session in which calibration was never started
SHALL carry no calibration field. A `calibrate` control message whose
action is neither `start` nor `cancel` SHALL be ignored.

#### Scenario: Progress is reported during capture
- **WHEN** calibration is running and a view has just been kept
- **THEN** the next telemetry message reports the capturing state and
  the updated view count

#### Scenario: Sessions that never calibrate are unchanged
- **WHEN** a session never starts calibration
- **THEN** its telemetry carries no calibration field
