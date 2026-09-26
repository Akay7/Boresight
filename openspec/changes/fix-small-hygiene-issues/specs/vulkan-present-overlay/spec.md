## ADDED Requirements

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
