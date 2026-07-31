# phone-client Specification

## Purpose
TBD - created by archiving change add-phone-video-stream. Update Purpose after archive.
## Requirements
### Requirement: The server serves a phone client requiring no installation
The server SHALL serve a self-contained browser page that turns a phone
into the barrel camera, requiring nothing installed on the phone beyond
a modern browser. The page SHALL be served by the same server that
receives its frames, so the address the phone loads is the address it
streams to and no second endpoint has to be configured.

#### Scenario: The client page is served by the frame server
- **WHEN** a browser requests the server's client page
- **THEN** the page is returned, and it derives the frame endpoint from
  the address it was loaded from rather than from a hardcoded host

### Requirement: The client is distributed as part of the package
The client's files SHALL be packaged inside the installable Python
package and located relative to the module that serves them, so an
installed copy serves the client without a source checkout present. The
failure this prevents is invisible to a test suite that always runs from
a checkout: files stored outside the packaged directory are omitted from
the built distribution, and the client 404s only once installed.

#### Scenario: The client is served without a source checkout
- **WHEN** the package is installed from a built distribution and the
  server is started with no repository checkout on the machine
- **THEN** requesting the client page returns it, rather than failing to
  locate the client's files

#### Scenario: The client files are present in the built distribution
- **WHEN** a distribution is built from the project
- **THEN** it contains the client's markup and script

### Requirement: Capture uses the rear camera at a requested resolution
The client SHALL request the environment-facing camera and a capture
resolution suitable for marker detection, and SHALL report the
resolution and camera actually granted, since a browser may substitute
either. Detection range is governed by pixels across a marker, so a
silently downgraded resolution changes what the system can do.

#### Scenario: Rear camera is requested and the granted stream reported
- **WHEN** the client starts capture
- **THEN** it requests the environment-facing camera at the configured
  resolution, and displays the resolution and facing mode actually
  granted

### Requirement: Exposure is pinned where the browser allows it
The client SHALL attempt to disable automatic exposure and pin it to a
fixed low value through the capture track's constraints, and SHALL
report whether the device accepted that. Paper markers beside a bright
panel in a dim room are a severe dynamic-range case, auto-exposure
chases the panel, and the markers underexpose to mud; this is the single
control that determines whether detection works. Where the device does
not expose the control, the client SHALL say so plainly rather than
appear to have succeeded.

#### Scenario: Exposure control is applied when supported
- **WHEN** the capture device reports support for manual exposure
- **THEN** the client applies a fixed exposure and reports it as pinned

#### Scenario: Missing exposure control is surfaced, not hidden
- **WHEN** the capture device does not support manual exposure
- **THEN** the client reports that exposure could not be pinned, so the
  resulting detection behaviour is attributable

### Requirement: Frames are encoded and sent without unbounded buffering
The client SHALL capture frames at a configurable target rate, encode
each as JPEG at a configurable quality, and send it as one binary
message carrying the client's own timestamp. It SHALL NOT enqueue a new
frame while the socket's buffer is still draining; it SHALL skip that
capture instead. A client-side backlog produces exactly the staleness
the server's drop policy exists to prevent, one hop earlier.

#### Scenario: Capture skips rather than queues when the socket is behind
- **WHEN** the WebSocket's buffered amount exceeds the configured
  threshold at capture time
- **THEN** the client skips that frame instead of buffering it, and
  counts the skip

#### Scenario: Each sent frame carries its own capture timestamp
- **WHEN** the client sends a frame
- **THEN** the binary message begins with the timestamp at which that
  frame was captured, so the server can report round-trip time

### Requirement: Connection state and telemetry are visible on the phone
The client SHALL display its connection state, the telemetry the server
sends back, and any capture or connection error, on the phone itself.
The person holding the gun cannot see the PC's console, and the
measurements that matter — round-trip time, frames dropped, markers
detected — are the ones they need while physically moving the camera
around.

#### Scenario: Server telemetry is displayed as it arrives
- **WHEN** the server sends a telemetry message during a session
- **THEN** the page updates to show the round-trip time, frame counts,
  and the most recent solve's marker count

#### Scenario: A failure is shown rather than logged silently
- **WHEN** camera access is denied, or the connection fails or closes
- **THEN** the page displays what happened, rather than leaving a blank
  or apparently-working screen

### Requirement: The secure-context requirement is explained where it is hit
The client SHALL detect an insecure origin and explain it, naming the
working alternatives, rather than failing with an unhandled error.
Browsers expose camera capture only in a secure context, so a phone
loading the client over plain HTTP from a LAN address has no camera API
at all — not a denied permission, an absent object.

#### Scenario: An insecure origin produces an explanation
- **WHEN** the client page is loaded from an origin the browser does not
  consider secure, so the media-devices API is unavailable
- **THEN** the page states that the camera is unavailable because the
  origin is not secure, and names the supported ways to reach it
  securely, rather than reporting a generic failure
