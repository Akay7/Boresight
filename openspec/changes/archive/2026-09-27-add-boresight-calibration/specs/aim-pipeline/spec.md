## ADDED Requirements

### Requirement: The per-frame operation applies a per-call aim correction
The per-frame operation SHALL accept an optional aim correction per
call and, when given one, SHALL use the corrected aim point in place of
the image-centre aim point for everything downstream of the solve:
the reported unclamped millimetre aim point, normalization, clamping,
the emitted position and the debug cursor position. The correction
SHALL be an argument rather than held on the pipeline, so that one
session's correction cannot change another's frames. Without a
correction the operation SHALL behave exactly as before. A solved
frame's result SHALL also carry the frame's solved geometry (its
homography, image size and screen size) for a caller that needs it,
without it taking part in result equality.

#### Scenario: No correction leaves the aim unchanged
- **WHEN** a frame is processed without a correction
- **THEN** the result and the emitted position are identical to those
  produced before corrections existed

#### Scenario: A correction moves the emitted position
- **WHEN** a frame is processed with a correction whose aim offset is
  non-zero
- **THEN** the emitted position is the corrected aim point normalized
  and clamped, and the debug cursor position no longer coincides with
  the image centre
