## ADDED Requirements

### Requirement: The overlay is placed on the chosen display
The overlay SHALL accept a display by name as well as by index, and the
server SHALL start it on the same display the cursor maps onto. Changing
the display while on-screen markers are active SHALL restart the overlay
on the new display, reporting a failure to restart the way selecting
on-screen markers does.

#### Scenario: Markers and cursor share a display
- **WHEN** display `HDMI-A-1` is chosen and on-screen markers are
  selected
- **THEN** the overlay is started on `HDMI-A-1`

#### Scenario: A display change moves the markers
- **WHEN** on-screen markers are active and the display is changed
- **THEN** the overlay is restarted on the new display
