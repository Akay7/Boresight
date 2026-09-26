## ADDED Requirements

### Requirement: The overlay draws a calibration target on request
When started by the server, the overlay SHALL accept commands to show
a single calibration target at a given full-screen pixel position, or
to hide it, and SHALL draw the target as an opaque patch visible over
arbitrary screen content. Drawing the target SHALL NOT make the overlay
receive input, and SHALL NOT change where the marker tags are drawn. An
overlay started directly, without the server, SHALL NOT read commands.

#### Scenario: A target appears where requested
- **WHEN** the server asks the running overlay to show a target at a
  pixel position
- **THEN** a target centred on that position is drawn over the display,
  and the marker tags are unchanged

#### Scenario: The target can be hidden
- **WHEN** the server asks the overlay to hide the target
- **THEN** no target is drawn, and only the marker tags remain

#### Scenario: Clicks still pass through a target
- **WHEN** a click is delivered over the drawn target
- **THEN** the application beneath receives it and the overlay does not
