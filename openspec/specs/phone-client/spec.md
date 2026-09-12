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

### Requirement: The client can choose the marker source
The client SHALL let the person holding the phone choose between
printed and on-screen markers, and SHALL show which is currently
active. The choice belongs here rather than only at the PC because that
is where the person is: standing at the display with the camera, not at
the keyboard.

#### Scenario: The current source is visible on the phone
- **WHEN** the client page is open
- **THEN** it shows whether printed or on-screen markers are currently
  active

#### Scenario: Choosing a source takes effect without reconnecting
- **WHEN** the person selects the other marker source while streaming
- **THEN** the selection is applied and the displayed state updates,
  without the video connection being restarted

### Requirement: A failed marker source selection is shown, not swallowed
Where selecting a marker source fails, the client SHALL display the
reason given by the server and SHALL continue to show the source that
is actually active. It SHALL NOT show the requested source as active
when it is not.

#### Scenario: An overlay that refused to start says so on the phone
- **WHEN** on-screen markers are selected and the server reports that
  the overlay could not start
- **THEN** the page shows that explanation and continues to show printed
  markers as the active source

### Requirement: The preview marks the point the camera is aiming at
The client SHALL draw a reticle at the centre of the camera preview
whenever the camera is running, derived from the preview's own geometry
and not from anything the server sends. The aim point is the image
centre pushed through the inverse homography, so the centre of the
element displaying that image is the aim point by construction; a mark
that depended on the server would go blank on exactly the frames — no
markers detected, solve failed, connection dropped — where the operator
most needs to know where the gun is pointed.

#### Scenario: The reticle is present as soon as the camera runs
- **WHEN** the client has started the camera
- **THEN** a reticle is drawn at the centre of the preview, before any
  frame has been sent or any telemetry received

#### Scenario: The reticle survives a dropout
- **WHEN** the server reports frames in which no markers were detected,
  or the connection closes while the camera is still running
- **THEN** the reticle remains drawn at the centre of the preview

#### Scenario: The reticle stays at the image centre when the preview is letterboxed
- **WHEN** the granted camera aspect ratio differs from the preview
  element's, so the video is letterboxed within it
- **THEN** the reticle is drawn at the centre of the displayed video
  content, which is the centre of the captured image

### Requirement: The operator can overlay the server's solve geometry on the preview
The client SHALL offer a control that turns per-frame debug geometry on
and off, and while it is on SHALL draw that geometry over the preview,
registered to the displayed image: each detected marker's outline and
ID, visually distinguishing markers the layout maps from markers it
ignores; the screen rectangle as projected by the solve; and the
emitted cursor position. Shapes SHALL be outlined rather than filled,
since the overlay exists to be compared against the image beneath it.
The control SHALL default to off and its state SHALL be re-sent when a
connection is established, so the setting survives a reconnect.

#### Scenario: The overlay is off until asked for
- **WHEN** the client starts streaming without the operator enabling
  the overlay
- **THEN** only the reticle is drawn, and the client does not request
  debug geometry from the server

#### Scenario: Enabling the overlay draws the server's geometry
- **WHEN** the operator enables the overlay during a session and the
  server reports a solved frame
- **THEN** the detected markers, the projected screen rectangle and the
  emitted cursor position are drawn over the preview at the image
  positions the server reported, scaled to the displayed video

#### Scenario: Ignored markers are distinguishable from mapped ones
- **WHEN** the overlay is on and a detected marker is absent from the
  active layout
- **THEN** it is drawn distinguishably from the mapped markers and
  labelled with its ID, so a tag being seen and skipped is
  distinguishable from one not being seen

#### Scenario: The setting survives a reconnect
- **WHEN** the overlay is enabled and the connection is re-established
- **THEN** the client re-requests debug geometry without the operator
  having to toggle the control again

### Requirement: The overlay never draws stale or unregistered geometry
The client SHALL clear the projected rectangle and cursor position when
a reported frame carries neither — because it did not solve — rather
than leave the previous frame's shapes on screen. Because the geometry
describes a frame captured a round trip earlier, the client SHALL show
how old the drawn geometry is and SHALL state that alignment is judged
with the camera held still. The client SHALL also display the frame
size the server decoded alongside the resolution the camera granted, so
a mismatch that would displace every drawn shape is visible rather than
silently scaled away.

#### Scenario: An unsolved frame clears the projected shapes
- **WHEN** the overlay is on and the server reports a frame that did
  not solve
- **THEN** the rectangle and cursor position are removed from the
  preview rather than retained from the previous frame

#### Scenario: The geometry's age is shown
- **WHEN** the overlay is on and telemetry is arriving
- **THEN** the client displays the age of the geometry it is drawing

#### Scenario: A resolution mismatch is stated
- **WHEN** the frame size the server reports decoding differs from the
  resolution the camera granted
- **THEN** the client displays both, rather than rescaling the geometry
  as though they agreed

### Requirement: The overlay reports how well the solve reprojects
While the overlay is on, the client SHALL display the reprojection
error the server reports, alongside — not instead of — the existing
conditioning indication for that solve. A fit from a single marker is
exact and reprojects at near zero error precisely when the aim point is
least trustworthy, so the number describes the fit's self-consistency
and never substitutes for whether the aim point lay within the markers.

#### Scenario: Reprojection error is shown next to the conditioning flag
- **WHEN** the overlay is on and the server reports a solved frame
- **THEN** the client displays the reprojection error, and continues to
  display whether the aim point was extrapolated beyond the visible
  markers
