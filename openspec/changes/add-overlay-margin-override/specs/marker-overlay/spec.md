## ADDED Requirements

### Requirement: A manual margin can extend automatic panel avoidance
The system SHALL accept a configurable extra margin that is subtracted
from all four sides of the automatically detected available area before
tags are placed within it, so a display environment that under-reports
what is actually reserved on a given monitor can be corrected without a
code change. Leaving the margin unset SHALL NOT change the automatically
detected area.

#### Scenario: An unset margin changes nothing
- **WHEN** the overlay is started without specifying an extra margin
- **THEN** tags are placed using exactly the automatically detected
  available area, as before this requirement existed

#### Scenario: A configured margin shrinks the usable area on every side
- **WHEN** the overlay is started with an extra margin specified
- **THEN** the area tags are placed within is smaller than the
  automatically detected available area by that margin on each side

#### Scenario: The margin is available wherever the overlay is started
- **WHEN** the overlay is started directly, or started by the server on
  a phone's request to switch to on-screen markers
- **THEN** a configured margin has the same effect either way

### Requirement: The margin can be changed while the server is running
The system SHALL accept a new margin value at runtime and, if on-screen
markers are currently active, SHALL restart the overlay with the new
value so the change is visible without a server restart.

#### Scenario: A new margin restarts an already-running overlay
- **WHEN** the margin is changed while on-screen markers are the active
  source
- **THEN** the overlay restarts using the new margin, and tags are
  placed accordingly on the next frame

#### Scenario: A margin changed while printed markers are active waits for the next switch
- **WHEN** the margin is changed while printed markers are the active
  source
- **THEN** nothing currently on screen changes, and the new value is
  used the next time on-screen markers are selected
