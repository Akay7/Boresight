## MODIFIED Requirements

### Requirement: Aim points beyond the panel edge are clamped before emission
The pipeline SHALL clamp normalized coordinates into `[margin, 1.0 -
margin]` before emitting them, for a small fixed margin, rather than
into the full `[0.0, 1.0]` range — both when the aim point is a
physical position that legitimately falls outside the active panel
(the cursor backend accepts only the clamped range) and when a
genuine, on-panel solve lands at or very near the panel's physical
edge. The cursor device the pipeline emits to is classified as a
touchscreen so it positions directly rather than through relative-
motion acceleration; several desktop environments bind an action (e.g.
show-desktop, edge-swipe overview) to a pointer reaching the literal
screen edge, which a value of exactly `0.0` or `1.0` would trigger
indistinguishably from a real touch. The pipeline SHALL report both
the unclamped millimetre aim point and whether clamping occurred, so
an off-panel aim is observable rather than silently indistinguishable
from an aim at the margin.

#### Scenario: An off-panel aim point is clamped, not rejected
- **WHEN** the solver returns an aim point beyond the panel edge
- **THEN** the emitted normalized coordinates lie within `[margin, 1.0
  - margin]`, not at the literal `0.0`/`1.0` edge
- **AND** the result reports the unclamped millimetre aim point and
  indicates that the emitted position was clamped

#### Scenario: A near-edge on-panel aim point never reaches the literal edge
- **WHEN** the solver returns an aim point on the panel but within the
  margin of its physical edge
- **THEN** the emitted normalized coordinates are still bounded away
  from the literal `0.0`/`1.0` edge by the margin
