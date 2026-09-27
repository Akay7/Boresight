# phone-client Specification

## Purpose
The browser page the server serves to a phone: camera capture and
streaming, the on-screen trigger, marker-source and overlay controls,
and the telemetry that shows whether it is working.

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

### Requirement: The client keeps the token out of its URLs
Once loaded, the client SHALL remove the token from the address shown
in the browser, and SHALL NOT put the token on the URL of any request
it makes — page resources, control requests, the marker-sheet link, or
the frame socket — relying on the session cookie the server issued
instead. A URL is copied into browser history, server logs and
screenshots; a cookie is not. Where the server refuses the frame
socket for want of a valid credential, the client SHALL say so and
direct the person to reopen the URL the server printed, since a stale
cookie from an earlier server run looks exactly like a missing one.

#### Scenario: The address bar is cleaned after load
- **WHEN** the client page is opened from a URL carrying the token
- **THEN** the address shown in the browser no longer carries the token,
  and every other part of the address is preserved

#### Scenario: Requests carry no token in their URLs
- **WHEN** the client fetches its script, reads or changes a setting, or
  opens the frame socket
- **THEN** none of those request URLs carries the token, and each is
  authorized by the session cookie

#### Scenario: A refused socket explains how to recover
- **WHEN** the server closes the frame socket with a policy-violation
  status
- **THEN** the page states that the credential was missing or invalid
  and to reopen the exact URL the server printed

### Requirement: The on-screen trigger is held while it is pressed
The client SHALL send a trigger `down` message when the trigger control
is pressed and a trigger `up` message when it is released, so holding
the control holds the button and a quick tap is a click. The client
SHALL send `up` for a held trigger whenever the press ends in any other
way: the pointer is cancelled or its capture is lost, the page is
hidden, or streaming stops. The client SHALL NOT send a second `down`
while the trigger is already held, nor an `up` when it is not, and
holding the control SHALL NOT open the browser's long-press menu or
select text.

#### Scenario: Holding the trigger holds the button
- **WHEN** the player presses the trigger, keeps it pressed, and later
  lets go
- **THEN** the client sends one `down` at the press and one `up` at the
  release

#### Scenario: Leaving the page releases the trigger
- **WHEN** the trigger is held and the page is hidden or the pointer is
  cancelled
- **THEN** the client sends `up`

#### Scenario: Stopping releases the trigger
- **WHEN** the trigger is held and streaming is stopped
- **THEN** the client sends `up` before the connection is closed

### Requirement: The client can adjust the on-screen overlay's manual margin
The client SHALL let the person holding the phone increase or decrease
the on-screen overlay's manual panel-avoidance margin, and SHALL show
its current value. The control belongs here for the same reason marker
source selection does: judging whether a tag now clears a taskbar
requires looking at the display, which is where the person holding the
phone is standing, not at the PC's own keyboard.

#### Scenario: The current margin is visible on the phone
- **WHEN** the client page is open
- **THEN** it shows the on-screen overlay's currently configured margin

#### Scenario: Adjusting the margin takes effect without reconnecting
- **WHEN** the person adjusts the margin while streaming
- **THEN** the new value is sent and the displayed value updates,
  without the video connection being restarted

### Requirement: An on-screen trigger sends trigger events on the frame connection
The client SHALL display a trigger control whose presses are sent as
trigger messages over the existing frame connection, requiring no
second connection or endpoint. Which messages a press and a release send
is specified by the trigger-hold capability. The control SHALL be
disabled until streaming has started, since there is no connection to
send it on before then.

#### Scenario: Pressing the trigger uses the existing connection
- **WHEN** the client is streaming and the player presses the trigger
  control
- **THEN** the client sends its trigger message on the existing frame
  WebSocket connection, and opens no other connection

#### Scenario: The trigger is unusable before streaming starts
- **WHEN** the client has not yet started streaming
- **THEN** the trigger control is disabled and pressing it sends
  nothing

### Requirement: Trigger telemetry is visible on the phone
The client SHALL display the count of trigger events the server has
acknowledged, using the same telemetry channel other session counters
already arrive on, so the player can confirm a press reached the
server.

#### Scenario: Acknowledged trigger count is displayed
- **WHEN** the server reports a trigger count in a stats message
- **THEN** the client updates the displayed count to match

### Requirement: The client identifies itself when its connection opens
The client SHALL send a `hello` control message identifying itself as a
phone, with the capture resolution it was granted, each time its frame
connection opens, including after a reconnect. With more than one kind
of client able to connect, the server's logs and session listing are
otherwise unable to say which device a session belongs to.

#### Scenario: Hello is sent on connect
- **WHEN** the client's frame connection opens
- **THEN** it sends a `hello` message naming the client kind `phone` and
  the granted capture resolution before or alongside its first frame

#### Scenario: Hello is re-sent after a reconnect
- **WHEN** the connection is re-established
- **THEN** the client sends `hello` again on the new connection

### Requirement: Frame timestamps mark the moment of capture
The client SHALL stamp each frame with the time the camera captured it,
taken from the browser's per-video-frame capture metadata where
available and otherwise from the client's monotonic clock at the moment
the frame is taken from the video element. The stamp SHALL NOT be taken
after the frame has been encoded, since encoding time varies from frame
to frame. The client SHALL NOT send a frame whose capture stamp equals
that of the frame it sent before, since it is the same picture.

#### Scenario: Encoding time does not enter the timestamp
- **WHEN** the client captures a frame and JPEG encoding it takes a
  variable amount of time
- **THEN** the timestamp sent with the frame is the capture time, and is
  unaffected by how long encoding took

#### Scenario: The same camera frame is not sent twice
- **WHEN** the capture timer fires again before the camera has
  delivered a new frame
- **THEN** the client sends nothing for that tick

### Requirement: The trigger names the frame it was aimed with
When the on-screen trigger is pressed, the client SHALL include in its
`down` message a `frame_ms` field holding the timestamp of the latest
frame it has sent on the current connection, so the server can fire at
that frame's aim point rather than at the smoothed cursor. If no frame
has been sent on the connection yet, the client SHALL omit the field.

#### Scenario: A press names the latest sent frame
- **WHEN** the client has sent frames and the player presses the
  trigger
- **THEN** the `down` message carries the timestamp of the most recent
  frame sent

#### Scenario: A press before any frame names none
- **WHEN** the player presses the trigger before any frame has been
  sent on the connection
- **THEN** the `down` message carries no `frame_ms`

### Requirement: The phone shows whether it drives the cursor
The client SHALL display, alongside its other telemetry, whether this
phone currently drives the cursor, another client does, or nobody does,
from the `cursor` field of the server's stats messages, so a player
whose aim is not moving the cursor can see why.

#### Scenario: Another client has the cursor
- **WHEN** the server's stats say `cursor` is `other`
- **THEN** the page shows that another device is driving the cursor

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

### Requirement: The client can zero the gun
The client SHALL offer controls to start zeroing, finish it, cancel it
and reset a stored zero, sending the corresponding zeroing control
messages on the frame connection. While a run is active it SHALL show
which target to shoot, its position in the sequence, whether it is
optional, and the outcome of the last shot. When the session is zeroed
it SHALL say so, with the fit's residual. The trigger SHALL keep working
unchanged; the server decides that a press during zeroing is a shot.

#### Scenario: The prompt names the target to shoot
- **WHEN** a zeroing run is active and the server reports the target
  "top-left corner"
- **THEN** the client shows that label and the target's position in the
  sequence

#### Scenario: Controls are unavailable without a connection
- **WHEN** the client is not streaming
- **THEN** the zeroing controls are disabled

### Requirement: The client sends a persistent identity
The client SHALL generate a random identifier once, keep it in the
browser's local storage, and include it as `id` in every `hello`, so the
server can recognise the same phone across reconnects and server
restarts. Where local storage is unavailable the `hello` SHALL be sent
without an `id`.

#### Scenario: The same id is sent after a reload
- **WHEN** the page is reloaded and streaming restarted
- **THEN** the `hello` carries the same `id` as before

### Requirement: The phone can save the last seconds of its stream
The client SHALL offer a control, available while streaming, that asks
the server to save this session's recent frames as a recording, and
SHALL display the directory the server reports having written and how
many frames it holds, or the reason the server gives for writing
nothing. The control SHALL send no credentials of its own: it rides the
already-authenticated frame connection.

#### Scenario: Saving shows where the recording went
- **WHEN** the operator presses the save control while streaming
- **THEN** the page shows the recording's directory and frame count once
  the server answers

#### Scenario: A refused save is explained
- **WHEN** the server answers that nothing was recorded
- **THEN** the page shows the server's reason rather than appearing to
  have saved

### Requirement: The phone can choose the display
The phone's settings panel SHALL list the server's displays and let the
user choose the one the gun aims at, showing the one in effect and any
reason a choice was refused.

#### Scenario: Choosing a display from the phone
- **WHEN** the user picks another display in the settings panel
- **THEN** the server is asked to apply it, and the panel shows the
  display in effect afterwards
