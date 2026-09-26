## ADDED Requirements

### Requirement: The per-frame operation corrects lens distortion when given a lens model
The per-frame operation SHALL accept an optional lens model (camera
matrix and distortion coefficients) per call. When one is given, it
SHALL undistort every detected marker corner into ideal pinhole pixel
coordinates with the same camera matrix before solving. It SHALL also
undistort the image centre the same way and aim through it, so the aim
point is still the point imaged at the frame's centre. It SHALL NOT
remap the whole frame. The lens model SHALL be passed per call rather
than held on the pipeline, because the pipeline is shared between
sessions whose cameras differ. When no lens model is given, the
operation SHALL behave exactly as it does without this requirement.

#### Scenario: No lens model changes nothing
- **WHEN** a frame is processed without a lens model
- **THEN** the result and the emitted position are identical to those
  produced before lens support existed

#### Scenario: A distorted frame is solved more accurately with its lens model
- **WHEN** a frame of the marker layout is rendered through a camera
  with known strong radial distortion and processed with that camera's
  lens model
- **THEN** the aim point is closer to the ground-truth aim point than
  when the same frame is processed without the lens model, and within
  a documented tolerance of it

#### Scenario: Debug geometry stays in raw image pixels
- **WHEN** a frame is processed with a lens model and debug output
  requested
- **THEN** detected marker corners are reported as detected, in raw
  image pixels, and the projected screen quad and cursor position are
  distorted back into raw image pixels, so an unclamped cursor lands on
  the image centre
