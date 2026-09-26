## ADDED Requirements

### Requirement: Smoothing parameters can change while streaming
The system SHALL let the smoothing's parameters — how strongly a slow
aim is smoothed, and how much speed reduces that — be changed while
sessions are streaming (see runtime-settings). A change SHALL apply to
every session from its next smoothed position without resetting the
session's smoothing state, so the cursor does not jump when the
parameters change, and each session SHALL use one consistent set of
parameters for any one position.

#### Scenario: Changing a parameter mid-stream does not jolt the cursor
- **WHEN** a session is holding a steady aim and a smoothing parameter
  is changed
- **THEN** the emitted cursor position stays where it was, with no jump
  attributable to the change, and later positions are smoothed with the
  new value
