# marker-overlay Specification

## Purpose
Render the marker layout as tags drawn directly on the live display
instead of printed on paper, so the tags are emissive, their positions
are known exactly rather than measured by hand, and a close-range
camera keeps seeing markers that sit inside the panel rather than
outside it. The overlay must be transparent to mouse and keyboard
input — the system injects its own clicks at the aim point, which lies
on the display the overlay covers, so an overlay that accepted input
would swallow the shots the gun fires. This covers where and how the
tags are drawn, the overlay's transparency to input, the shared layout
computation that keeps the drawn and solved positions identical, the
coordinate convention that layout is expressed in, keeping tags
detectable against arbitrary screen content, per-platform availability
and its diagnostics, the overlay's optional install footprint, and its
place alongside printed markers as an alternative rather than a
replacement.

## Requirements
### Requirement: Markers are drawn over the live display
The system SHALL render the marker layout as tags drawn on top of
whatever is already shown on the display, without altering, moving or
resizing the application beneath. The tags SHALL remain visible above
other windows while the overlay is running.

#### Scenario: Tags appear over existing screen content
- **WHEN** the overlay is started while an application is showing on the
  target display
- **THEN** the marker tags are drawn on top of that application's output
- **AND** the application beneath is neither moved, resized, nor
  otherwise modified

#### Scenario: Tags stay above other windows
- **WHEN** another window is raised or focused while the overlay is
  running
- **THEN** the tags remain visible above it

### Requirement: The overlay is transparent to mouse and keyboard input
The overlay SHALL NOT receive, consume or intercept any mouse or
keyboard event. Every event over the overlay's area SHALL reach the
application beneath exactly as though the overlay were not present,
including clicks landing on the tags themselves. This is not a
convenience: the system injects its own clicks at the aim point, which
lies on the display the overlay covers, so an overlay that accepted
input would swallow the shots the gun fires.

#### Scenario: A click over a tag reaches the application beneath
- **WHEN** a mouse click is delivered at a position covered by a marker
  tag
- **THEN** the application beneath receives that click at that position
- **AND** the overlay receives nothing

#### Scenario: Injected clicks are not swallowed by the overlay
- **WHEN** the system injects a click at an aim point that falls over
  the overlay
- **THEN** the click is delivered to the application beneath rather than
  to the overlay

#### Scenario: Keyboard input is unaffected
- **WHEN** the overlay is running and keyboard input is sent to the
  focused application
- **THEN** the focused application receives it, and the overlay neither
  takes focus nor consumes keystrokes

### Requirement: The drawn layout and the solved layout are the same layout
The system SHALL derive the positions the overlay draws and the
positions the solver is given from a single computation over the same
display geometry, so the two cannot disagree. It SHALL NOT require a
file to be written, a message to be passed, or a value to be
transcribed, between rendering a tag and solving against it.

#### Scenario: Renderer and solver agree without coordination
- **WHEN** the overlay renders a layout for a given display geometry and
  tag configuration, and the solver is separately given the layout for
  that same geometry and configuration
- **THEN** the marker positions are identical, with no file or message
  exchanged between them

#### Scenario: Changing the configuration moves both together
- **WHEN** the tag size or inset is changed
- **THEN** the rendered positions and the solved positions both change
  to match, and remain equal to one another

### Requirement: The layout is expressed in the units the solver already uses
The derived layout SHALL be expressed in the same coordinate convention
a printed layout uses — an origin at the top-left of the active display
area, x rightwards and y downwards — so that a consumer cannot tell a
screen-derived layout from a file-loaded one. Screen positions SHALL be
converted with a single uniform scale for both axes, so that the display
aspect ratio is preserved and any error in the assumed scale cancels
when the aim point is normalized.

#### Scenario: A derived layout is interchangeable with a loaded one
- **WHEN** the pipeline is given a layout derived from the display
  instead of one loaded from a file
- **THEN** it solves and emits exactly as it does with a loaded layout,
  with no special handling

#### Scenario: The assumed scale does not affect the aim point
- **WHEN** the same display geometry is converted using two different
  uniform scales
- **THEN** the normalized aim point produced for a given camera view is
  the same in both cases

### Requirement: Tags remain detectable against arbitrary screen content
Each tag SHALL be drawn over a solid quiet-zone patch rather than
composited onto the pixels beneath it, so that detection does not depend
on what the application underneath happens to be displaying. The patch
SHALL extend beyond the tag on every side.

#### Scenario: A tag over bright content is still decodable
- **WHEN** a tag is drawn over screen content of arbitrary brightness
  and detail
- **THEN** the rendered tag is surrounded by its quiet-zone patch, and
  the underlying content does not appear within the tag or its quiet
  zone

### Requirement: The overlay states plainly where it cannot run
The overlay SHALL detect at startup whether the current display
environment can host an always-on-top, input-transparent surface, and
SHALL refuse to start with an explanatory message naming printed markers
as the alternative where it cannot. It SHALL NOT present a window that
appears to work while intercepting input, and SHALL NOT fail with an
unhandled error from a windowing library.

#### Scenario: An unsupported compositor is reported, not worked around
- **WHEN** the overlay is started in a display environment that does not
  permit a client to place an always-on-top surface
- **THEN** it exits with a message identifying the environment as
  unsupported and naming printed markers as the alternative

#### Scenario: A supported environment starts normally
- **WHEN** the overlay is started in a display environment that permits
  such a surface
- **THEN** it starts and renders the tags

### Requirement: The overlay is optional and does not burden a default install
The overlay's user-interface dependencies SHALL be declared as an
optional install group. Installing the project without that group SHALL
leave the server, pipeline, detector and solver fully functional, and
SHALL NOT install a graphical toolkit.

#### Scenario: A default install omits the interface dependencies
- **WHEN** the project is installed without the overlay group
- **THEN** the graphical toolkit is absent, and the server, pipeline and
  solver run normally

#### Scenario: Requesting the overlay without its dependencies is explained
- **WHEN** the overlay is started in an installation that omits the
  overlay group
- **THEN** it reports which group to install rather than raising an
  import error

### Requirement: Printed and on-screen layouts are alternatives, not a replacement
The system SHALL let the marker layout source be selected by
configuration, and SHALL continue to support a layout loaded from a
file exactly as before. Choosing an on-screen layout SHALL NOT be
required in order to use the rest of the system.

#### Scenario: A printed layout still works
- **WHEN** the system is configured to use a layout loaded from a file
- **THEN** it behaves exactly as it did before the overlay existed

#### Scenario: The layout source is selectable
- **WHEN** the system is configured to use an on-screen layout
- **THEN** the pipeline solves against the overlay's derived layout
  rather than a file
