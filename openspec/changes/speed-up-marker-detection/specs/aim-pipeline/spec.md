## ADDED Requirements

### Requirement: A caller supplies its own per-session detector per call
The per-frame operation SHALL accept, per call, the detector state of
the session the frame belongs to, and SHALL detect that frame through
it without retaining it, so the pipeline itself stays stateless and
shareable between sessions. The pipeline SHALL be able to create a new
per-session detector on request; when the pipeline was built with a
substitute detector (as tests do), or with tracking disabled, the
per-session detector it creates SHALL be that detector unchanged.
Replaying a recorded sequence SHALL detect it through one per-session
detector, as one streaming session would.

#### Scenario: A per-call detector is used and not kept
- **WHEN** a frame is processed with a per-session detector supplied,
  and then another frame is processed without one
- **THEN** the first frame is detected through the supplied detector,
  and the second through the pipeline's own detector

#### Scenario: A substitute detector is not bypassed
- **WHEN** a pipeline built with a substitute detector is asked for a
  per-session detector
- **THEN** it returns the substitute detector, so frames processed with
  it see exactly the substitute's detections
