## ADDED Requirements

### Requirement: The phone can choose the display
The phone's settings panel SHALL list the server's displays and let the
user choose the one the gun aims at, showing the one in effect and any
reason a choice was refused.

#### Scenario: Choosing a display from the phone
- **WHEN** the user picks another display in the settings panel
- **THEN** the server is asked to apply it, and the panel shows the
  display in effect afterwards
