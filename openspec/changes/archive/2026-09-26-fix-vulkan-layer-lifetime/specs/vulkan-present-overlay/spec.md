## Purpose

Draws the marker patches inside a Vulkan-presenting application's own
frames, so they remain visible over content a window-based overlay
cannot reach — exclusive fullscreen — by acting inside the
application's presentation path rather than as a separate window.

## ADDED Requirements

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
