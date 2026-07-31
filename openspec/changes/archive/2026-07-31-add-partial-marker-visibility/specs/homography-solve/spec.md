## ADDED Requirements

### Requirement: Solver reports the geometric conditioning of each solve
The solver SHALL report, alongside the aim point, whether that aim point
lies inside the convex hull of the screen-plane correspondence points,
the signed distance from the aim point to that hull in millimetres, and
the extent of the correspondence points. Reprojection error SHALL NOT be
relied upon for this purpose: an exactly-determined fit from a single
marker has near-zero reprojection error while its aim point may be
badly wrong, so reprojection error is anti-correlated with accuracy in
exactly the case this signal exists to flag.

#### Scenario: Aim point inside the marker footprint is reported as interpolated
- **WHEN** the solver is given correspondences from markers spread
  around the aim point, so that the aim point falls within their convex
  hull
- **THEN** the result reports the aim point as inside the hull, with a
  signed distance indicating it is interior

#### Scenario: Aim point beyond the marker footprint is reported as extrapolated
- **WHEN** the solver is given correspondences from a single marker, or
  from markers clustered such that the aim point falls outside their
  convex hull
- **THEN** the result reports the aim point as outside the hull, with a
  signed distance indicating how far beyond the fitted region it lies

#### Scenario: Conditioning is reported without changing the aim point
- **WHEN** the same correspondences are solved
- **THEN** the reported aim point is identical to what the solver would
  produce without the conditioning fields, which are additional data and
  never alter the solution

### Requirement: Solver degrades predictably as marker visibility drops
The solver SHALL return a best-effort aim point whenever at least four
correspondences are available, regardless of how poorly those
correspondences are distributed, and SHALL NOT refuse or substitute a
fallback value on conditioning grounds alone. Deciding what to do about
a poorly conditioned aim point is the consumer's responsibility.

#### Scenario: A well-distributed subset of markers stays accurate
- **WHEN** only some markers are visible but they span the aim point --
  for example markers on opposite sides of the panel
- **THEN** the recovered aim point matches ground truth within a
  documented tolerance comparable to the full-visibility case

#### Scenario: A poorly distributed subset still returns an answer, flagged
- **WHEN** only markers clustered on one edge, or a single marker, are
  visible, so the aim point is extrapolated well outside them
- **THEN** the solver still returns an aim point rather than raising
- **AND** the result's conditioning fields report the aim point as
  outside the correspondence hull

#### Scenario: No visible markers cannot be solved
- **WHEN** a frame contains no detectable markers, so fewer than four
  correspondences are available
- **THEN** the solver raises the insufficient-correspondences error
  rather than returning an aim point
