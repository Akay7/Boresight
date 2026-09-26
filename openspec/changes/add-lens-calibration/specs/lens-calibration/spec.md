## Purpose

Measures a streaming camera's intrinsics and lens distortion from views
of a ChArUco board. Stores the result per client, camera and resolution
so the aim pipeline can correct for that camera's lens.

## ADDED Requirements

### Requirement: Calibration captures varied board views from a session's own frames
The server SHALL, once calibration is started for a streaming session,
look for the ChArUco calibration board in that session's frames and
keep a frame's board corners as a calibration view only when enough of
the board's inner corners are found (at least half of them, not all
collinear). A kept view SHALL also differ from every view already kept:
either its corners moved noticeably relative to the image width, or it
shares too few corners with that view. Frames SHALL NOT be taken from
any other session. When the session's frame resolution changes during
capture, the views already kept SHALL be discarded and capture SHALL
start over at the new resolution.

#### Scenario: A board held still yields one view
- **WHEN** calibration is running and the session streams many frames of
  the board without moving it
- **THEN** exactly one view is kept

#### Scenario: A moved board yields another view
- **WHEN** the board is then moved to a clearly different place in the
  frame
- **THEN** a second view is kept

#### Scenario: Frames without enough of the board are not kept
- **WHEN** a frame shows no board, or shows fewer than half of its inner
  corners
- **THEN** no view is kept from that frame and capture continues

#### Scenario: A resolution change restarts capture
- **WHEN** views have been kept and the session's frame size changes
- **THEN** the kept views are discarded and counting starts again from
  the first frame at the new size

### Requirement: Calibration reports its reprojection error and stores good results
Once the configured number of views has been kept, the server SHALL
compute the camera matrix and distortion coefficients from them and
report the RMS reprojection error in pixels. When that error is within
the acceptance bound, the result SHALL be stored and SHALL replace any
earlier result under the same key. When it is not, the result SHALL be
reported as failed with its error and SHALL NOT be stored. Either way
the session's aim continues uninterrupted.

#### Scenario: Synthetic distorted views recover the distortion
- **WHEN** calibration is fed views of the board rendered through a
  camera with known intrinsics and known radial and tangential
  distortion
- **THEN** it reports an RMS reprojection error below one pixel
- **AND** undistorting points across the frame with the recovered model
  agrees with the known model to within a pixel

#### Scenario: A poor fit is not stored
- **WHEN** the computed RMS reprojection error exceeds the acceptance
  bound
- **THEN** calibration is reported as failed with that error, and
  nothing is written to the store

### Requirement: Calibrations are keyed by client, camera and resolution
A stored calibration SHALL be keyed by the session's client kind (from
its `hello`, or unidentified), the camera label from its `hello` when
one was given, and the pixel size of the frames it was computed from.
It SHALL be applied only to a session whose key matches exactly, and
SHALL NOT be scaled to or reused for another resolution. Calibrations
SHALL persist across server restarts in `.boresight/lenses.json`, and a
missing or unreadable store SHALL be treated as holding no
calibrations rather than stopping the server.

#### Scenario: A calibration survives a restart
- **WHEN** a calibration is stored and the server is restarted
- **THEN** a session with the same client kind, camera label and frame
  size has that calibration applied

#### Scenario: Another resolution is uncalibrated
- **WHEN** a session with the same client kind and camera streams at a
  different frame size
- **THEN** no calibration is applied to it

#### Scenario: A corrupt store is treated as empty
- **WHEN** `.boresight/lenses.json` cannot be parsed
- **THEN** the server starts, logs a warning, and applies no calibration

### Requirement: Calibration can be started from the phone or over HTTP
The server SHALL start or cancel calibration for a session on a
`calibrate` control message sent on that session's frame connection. It
SHALL also do so on an HTTP request that names the session by the
address the session listing reports, so that a client with no screen of
its own can be calibrated from another device. The address MAY be
omitted when exactly one session is connected. The HTTP request SHALL
be refused when the named session does not exist, or when no address is
given and the choice is ambiguous. The server SHALL also list the
stored calibrations, with their key, frame size, reprojection error and
when they were made. Both endpoints SHALL be covered by the same token
requirement as every other endpoint.

#### Scenario: Starting over HTTP with one session connected
- **WHEN** one session is streaming and calibration is started over
  HTTP without naming it
- **THEN** calibration runs on that session's frames

#### Scenario: An ambiguous request is refused
- **WHEN** two sessions are connected and calibration is started over
  HTTP without naming either
- **THEN** the request is refused and neither session starts
  calibration

#### Scenario: An unknown session is refused
- **WHEN** calibration is started over HTTP naming an address with no
  session
- **THEN** the request is refused with a not-found status

#### Scenario: Stored calibrations are listed
- **WHEN** the calibration listing is requested after a calibration was
  stored
- **THEN** it includes that calibration's key, frame size and RMS
  reprojection error
