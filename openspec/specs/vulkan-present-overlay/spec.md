# vulkan-present-overlay Specification

## Purpose
Draws the marker patches inside a Vulkan-presenting application's own
frames, so they remain visible over content a window-based overlay
cannot reach — exclusive fullscreen — by acting inside the
application's presentation path rather than as a separate window.

## Requirements

### Requirement: Destroying a Vulkan instance is prompt and leaves no layer work behind
The layer SHALL finish all of its own work tied to a `VkInstance` —
including the startup diagnostic — before that instance's destruction
returns, and SHALL NOT delay that destruction by waiting out the
startup diagnostic's timeout. After an instance is destroyed, the layer
SHALL NOT read or write any state belonging to it.

#### Scenario: A probe instance is created and destroyed at startup
- **WHEN** an application with the layer enabled creates a `VkInstance`
  and destroys it well before the startup diagnostic's timeout elapses
  (as DXVK/Proton and many engines do while probing)
- **THEN** `vkDestroyInstance` returns without waiting for the timeout,
  no startup diagnostic is logged for that instance, and the layer
  performs no later access to that instance's state

#### Scenario: Many instances are created and destroyed in quick succession
- **WHEN** an application creates and destroys many instances back to
  back with the layer enabled
- **THEN** the application neither crashes nor stalls for a timeout per
  instance, and no layer thread is left running for any destroyed
  instance

#### Scenario: The startup diagnostic still fires for a live instance
- **WHEN** an instance stays alive past the startup timeout without any
  swapchain having been created
- **THEN** the layer logs the actionable "no Vulkan swapchain"
  diagnostic exactly once for that instance

### Requirement: Host memory exhaustion in the layer never crashes the application
When a host allocation the layer makes for its own bookkeeping fails,
the layer SHALL NOT crash or corrupt the application's process. Failure
to allocate state for a new instance or device SHALL make that creation
call fail with `VK_ERROR_OUT_OF_HOST_MEMORY`, with any object the rest
of the chain already created for it destroyed again. Failure to allocate
state for a new swapchain SHALL leave that swapchain created and usable,
with this layer drawing nothing into it.

#### Scenario: Instance bookkeeping cannot be allocated
- **WHEN** the layer cannot allocate its per-instance state during
  `vkCreateInstance`
- **THEN** `vkCreateInstance` returns `VK_ERROR_OUT_OF_HOST_MEMORY` and
  no instance is leaked by the layer

#### Scenario: Swapchain bookkeeping cannot be allocated
- **WHEN** the layer cannot allocate its per-swapchain state during
  `vkCreateSwapchainKHR`
- **THEN** the swapchain is still created and presented normally, with
  no marker patches drawn into it

### Requirement: Layer-owned GPU resources do not outlive their device
The layer SHALL destroy every Vulkan object it created on a device's
behalf before passing that device's destruction down the chain, even
when the application destroys the device without first destroying a
swapchain the layer was drawing into.

#### Scenario: The device is destroyed with a swapchain still alive
- **WHEN** an application destroys a `VkDevice` while a swapchain the
  layer set up drawing for still exists
- **THEN** the layer's own canvas image, memory, command pool and
  semaphores for that swapchain are destroyed before the device is

### Requirement: A malformed marker canvas is rejected rather than drawn
The layer SHALL only draw from a marker canvas whose every rectangle is
non-empty and lies entirely inside the canvas (`x + w <= width`,
`y + h <= height`, evaluated without integer overflow), whose width and
height are each between 1 and 16384 pixels, whose rectangle count is at
most 4096, and whose file holds at least the rectangle and pixel data
its header declares. Any other canvas SHALL be treated exactly like a
missing canvas: the layer logs that it could not read a valid canvas
and passes every present through unmodified. Canvases produced by
Boresight's own canvas writer for a supported resolution SHALL always
satisfy these conditions.

#### Scenario: A rectangle extends past the canvas edge
- **WHEN** the configured canvas contains a rectangle with `x + w`
  greater than the canvas width (or `y + h` greater than its height)
- **THEN** the layer draws no marker patches from that canvas, logs
  that the canvas is invalid, and every frame is presented unmodified

#### Scenario: Rectangle coordinates overflow
- **WHEN** a rectangle's `x + w` or `y + h` would overflow a 32-bit
  unsigned integer
- **THEN** the canvas is rejected the same way as an out-of-bounds
  rectangle

#### Scenario: The header declares more data than the file holds
- **WHEN** the canvas header declares a rectangle count or pixel size
  larger than the file actually contains, or beyond the limits above
- **THEN** the canvas is rejected without the layer allocating memory
  for the declared size

#### Scenario: A canvas written by Boresight loads
- **WHEN** the canvas was written by Boresight's own canvas writer for
  the application's resolution
- **THEN** the layer accepts it and draws its marker patches

#### Scenario: Both canvas readers agree
- **WHEN** Boresight's Python canvas reader is given a canvas the layer
  would reject for any of the reasons above
- **THEN** it rejects that canvas too

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

### Requirement: Marker patches are only copied inside the swapchain image
The layer SHALL draw from a marker canvas into a swapchain only when the
canvas's width and height equal that swapchain's image extent exactly,
and every marker rectangle it copies SHALL lie entirely inside that
extent (`x + w <= width`, `y + h <= height`, evaluated without integer
overflow). A canvas that fails either check SHALL be treated like a
missing canvas for that swapchain: the layer logs why and passes every
present through unmodified.

#### Scenario: The canvas was generated for a different resolution
- **WHEN** the configured canvas is larger or smaller than the
  swapchain's image extent in either dimension
- **THEN** the layer draws no marker patches into that swapchain, logs
  both sizes, and every frame is presented unmodified

#### Scenario: The canvas matches the swapchain
- **WHEN** the configured canvas has exactly the swapchain's extent and
  every rectangle lies inside it, including rectangles that touch the
  right or bottom edge
- **THEN** the layer draws the marker patches

#### Scenario: Boresight's writer is given a rectangle the layer would reject
- **WHEN** Boresight is asked to write a canvas containing an empty
  rectangle or one that extends past the canvas edge
- **THEN** it refuses to write the file and reports the offending
  rectangle, rather than leaving the layer to reject it later
