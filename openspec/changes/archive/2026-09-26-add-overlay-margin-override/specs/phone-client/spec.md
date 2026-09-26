## ADDED Requirements

### Requirement: The client can adjust the on-screen overlay's manual margin
The client SHALL let the person holding the phone increase or decrease
the on-screen overlay's manual panel-avoidance margin, and SHALL show
its current value. The control belongs here for the same reason marker
source selection does: judging whether a tag now clears a taskbar
requires looking at the display, which is where the person holding the
phone is standing, not at the PC's own keyboard.

#### Scenario: The current margin is visible on the phone
- **WHEN** the client page is open
- **THEN** it shows the on-screen overlay's currently configured margin

#### Scenario: Adjusting the margin takes effect without reconnecting
- **WHEN** the person adjusts the margin while streaming
- **THEN** the new value is sent and the displayed value updates,
  without the video connection being restarted
