## ADDED Requirements

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
