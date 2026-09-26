## ADDED Requirements

### Requirement: The client can calibrate its lens
The client SHALL offer a control that starts lens calibration for its
own session, and another that cancels one in progress, sent as
`calibrate` control messages on its frame connection. It SHALL show the
calibration status the server reports: views kept out of views needed
while capturing, and the RMS reprojection error or the failure once
finished. It SHALL link to the calibration board page. The control
SHALL be unavailable while the client is not streaming.

#### Scenario: Starting calibration from the phone
- **WHEN** the operator presses the calibrate control while streaming
- **THEN** the client sends a `calibrate` message with action `start`
  and shows the server's progress as it is reported

#### Scenario: Result is shown
- **WHEN** the server reports the calibration as done
- **THEN** the client shows the RMS reprojection error

### Requirement: The client names its camera in hello
The client SHALL include the label of the camera track it is streaming
from as `camera` in its `hello`, when the browser exposes one, so a
calibration is kept per camera rather than per phone model.

#### Scenario: Camera label sent
- **WHEN** the connection opens and the browser reports a non-empty
  track label
- **THEN** `hello` carries that label as `camera`
