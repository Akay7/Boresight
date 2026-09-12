## Purpose

Draws the marker patches inside a Vulkan-presenting application's own
frames, so they remain visible over content a window-based overlay
cannot reach — exclusive fullscreen — by acting inside the
application's presentation path rather than as a separate window.

## ADDED Requirements

### Requirement: Marker patches appear in a Vulkan-presenting application's own frames
The system SHALL make the marker patches visible in every frame a
Vulkan-presenting application submits for display, once enabled for
that application's process, without that application's own rendering
being altered, moved, or resized.

#### Scenario: Patches appear over a fullscreen application
- **WHEN** the layer is enabled for an application that presents via
  Vulkan and is running exclusive fullscreen
- **THEN** the marker patches are visible on screen over that
  application's own content

#### Scenario: The application's own rendering is untouched outside the patches
- **WHEN** a frame is presented with the layer enabled
- **THEN** every pixel outside the marker rectangles matches what the
  application itself submitted, unmodified

### Requirement: The drawn layout matches the shared marker layout
The patches drawn by this backend SHALL use the same marker layout
computation the window-based overlay uses (`marker-overlay`'s layout
and rectangle geometry) for the same display resolution, so a consumer
solving against either backend's output sees the same marker positions.

#### Scenario: Same resolution, same positions as the window overlay
- **WHEN** this backend and the window-based overlay are each given the
  same display resolution and tag configuration
- **THEN** the marker rectangles and tag content they produce are
  identical

### Requirement: Enabling the layer does not change application input or behavior
The system SHALL NOT alter the input the application receives, its
frame timing correctness, or its own rendering output, beyond drawing
into the marker rectangles.

#### Scenario: Application input is unaffected
- **WHEN** the layer is enabled for an application
- **THEN** mouse, keyboard and controller input reach that application
  exactly as they would with the layer disabled

### Requirement: The layer tracks the current swapchain, not a stale one
When an application resizes its output or recreates its swapchain (for
example, a resolution change), the system SHALL recompute the marker
layout for the new dimensions rather than continuing to draw a layout
sized for a previous swapchain.

#### Scenario: A resolution change updates marker positions
- **WHEN** an application with the layer enabled changes its
  presentation resolution
- **THEN** subsequent frames show the marker patches positioned for the
  new resolution, not the previous one

### Requirement: Presented frames remain valid after the layer runs
The system SHALL hand every frame back to the presentation engine in
the image state and layout it expects, regardless of whether that
frame's marker rectangles were drawn successfully.

#### Scenario: A frame is presentable even if drawing the patches fails
- **WHEN** the layer's own drawing work for a frame fails or is skipped
  for any reason
- **THEN** that frame is still handed to the presentation engine in a
  valid, presentable state

### Requirement: The layer is enabled explicitly, per application
The system SHALL only draw marker patches into an application that has
been explicitly opted in for this backend. It SHALL NOT be active for
Vulkan applications generally as a result of being installed on a
system.

#### Scenario: An application not opted in is unaffected
- **WHEN** an application presents via Vulkan on a system where this
  backend is installed, but that application was not explicitly opted
  in
- **THEN** no marker patches appear in that application's frames

### Requirement: An application that cannot host this backend fails with an actionable diagnostic
The system SHALL detect, before or at the point marker drawing would
begin, whether the target application presents in a way this backend
can draw into. When it cannot — the application does not present via
Vulkan, or no compatible Vulkan loader is present — the system SHALL
report why, rather than running with no visible effect, and SHALL name
the window-based overlay and printed markers as alternatives.

#### Scenario: A non-Vulkan application gives a clear reason
- **WHEN** this backend is enabled for an application that does not
  present via Vulkan
- **THEN** the system reports that the application does not present via
  Vulkan and names the window-based overlay or printed markers as
  alternatives, rather than silently drawing nothing

#### Scenario: A missing Vulkan loader gives a clear reason
- **WHEN** this backend is enabled in an environment with no compatible
  Vulkan loader available
- **THEN** the system reports that no compatible Vulkan loader was
  found and names the window-based overlay or printed markers as
  alternatives
