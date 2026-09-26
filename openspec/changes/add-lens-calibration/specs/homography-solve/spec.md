## ADDED Requirements

### Requirement: Solver can aim through a given image point
The solver SHALL accept an optional image-plane point to map through the
inverse homography in place of the image centre. When none is given, it
SHALL map the image centre exactly as before. This lets a caller that
has undistorted the corners also undistort the point it aims through,
so both are in the same coordinates.

#### Scenario: Omitting the point aims through the image centre
- **WHEN** the solver is called without an aim point
- **THEN** the result is identical to mapping the image centre

#### Scenario: A given point is mapped instead
- **WHEN** the solver is called with an explicit image-plane aim point
- **THEN** the returned aim point is that image point mapped through the
  inverse of the fitted homography
