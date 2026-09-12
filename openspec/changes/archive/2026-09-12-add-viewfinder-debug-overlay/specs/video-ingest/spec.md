## ADDED Requirements

### Requirement: A session can request per-frame debug geometry
The server SHALL accept a JSON control message on the frame
connection's existing text channel by which a client turns per-frame
debug geometry on or off for its own session, and SHALL honour it from
the next processed frame onward. The setting SHALL belong to the
session rather than to the server, so one client enabling it does not
change what another client receives, and SHALL be re-settable at any
time during a session, including immediately after a reconnect.

#### Scenario: Debug geometry is enabled by a control message
- **WHEN** a connected client sends the debug control message with
  debug enabled
- **THEN** subsequent telemetry messages for that session carry the
  pipeline's debug geometry for the frame they report

#### Scenario: Debug geometry is turned off again
- **WHEN** a client that enabled debug geometry sends the control
  message with it disabled
- **THEN** subsequent telemetry messages for that session no longer
  carry the debug fields

#### Scenario: The setting does not leak between sessions
- **WHEN** one client enables debug geometry while a second client is
  streaming on its own connection
- **THEN** the second client's telemetry is unaffected

### Requirement: Telemetry is unchanged for sessions that do not ask
The telemetry payload SHALL omit the debug fields entirely — not send
them as empty or null — for any session that has not enabled debug
geometry, so that a client written against the existing payload
receives exactly what it receives today and a client that never asked
cannot render a partial overlay.

#### Scenario: A session that never asks sees the existing payload
- **WHEN** a client streams frames without ever sending the debug
  control message
- **THEN** every telemetry message it receives contains the same set of
  fields as before this change, with no debug keys present

### Requirement: Debug telemetry carries the frame's geometry and fit quality
When debug geometry is enabled, each telemetry message SHALL carry, for
the frame it reports, the decoded frame's pixel size, the detected
markers with their IDs, image-pixel corners and mapped status, and —
when that frame solved — the projected screen rectangle, the emitted
cursor position in image pixels, and the reprojection error of the fit.
The decoded size is reported rather than assumed to match the client's
capture resolution, because a browser may grant a different resolution
than the one requested and a silent mismatch would displace every drawn
shape.

#### Scenario: A solved frame reports full geometry
- **WHEN** a session with debug geometry enabled sends a frame that
  solves
- **THEN** its telemetry message carries the decoded image size, the
  detections, the projected screen rectangle, the cursor position in
  image pixels, and the reprojection error

#### Scenario: An unsolved frame reports what there was
- **WHEN** a session with debug geometry enabled sends a frame that
  does not solve
- **THEN** its telemetry message carries the decoded image size and any
  detections, and carries no rectangle, cursor position or reprojection
  error from that or any previous frame

#### Scenario: Reprojection error accompanies the conditioning flag
- **WHEN** a telemetry message reports a solved frame with debug
  geometry enabled
- **THEN** it carries the reprojection error in addition to, not in
  place of, the existing conditioning flag for that solve
