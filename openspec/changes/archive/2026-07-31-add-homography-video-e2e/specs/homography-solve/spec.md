## ADDED Requirements

### Requirement: Per-frame solver output forms a temporally coherent trajectory
The system SHALL produce a temporally coherent trajectory of aim points
when the solver is applied independently, once per frame, to each frame
of a temporally coherent input sequence (a smoothly moving camera
observing a fixed marker layout): consecutive-frame aim points SHALL
track the known consecutive-frame camera motion, without discontinuities
the input motion does not justify. The solver holds no state between
calls; this requirement constrains the trajectory formed by independent
per-call outputs, not any internal temporal logic.

#### Scenario: Consecutive frames of a smooth camera sweep produce a smooth aim-point trajectory
- **WHEN** the solver is called once per frame, in order, on
  correspondences detected from each frame of a rendered sequence
  depicting a smoothly moving camera
- **THEN** for each pair of consecutive frames, the difference between
  their recovered aim points matches the difference between their known
  ground-truth aim points, within a documented tolerance

#### Scenario: Each frame's recovered aim point matches its own ground truth
- **WHEN** the solver is called on correspondences detected from a single
  frame of the sequence
- **THEN** the recovered aim point matches that frame's independently
  computed ground-truth aim point (derived from the rendering camera's
  known pose, not from the solver's own homography math) within a
  documented tolerance
