## ADDED Requirements

### Requirement: The cursor backend supports a discrete click
The cursor backend interface SHALL expose a click operation, distinct
from absolute movement, that presses and releases the primary button at
the cursor's current position. On Linux, this SHALL be implemented via
the same `uinput` virtual device already used for positioning, using a
button code distinct from the one `move_absolute` uses internally, so a
click is distinguishable from the touch events positioning already
generates on every call.

#### Scenario: A click presses and releases the primary button
- **WHEN** the cursor backend's click operation is invoked
- **THEN** the OS observes a primary-button press followed by a release
  at the cursor's current position, with no change to that position

#### Scenario: A click does not move the cursor
- **WHEN** the cursor is at an arbitrary position and the click
  operation is invoked
- **THEN** the cursor remains at that position after the click
  completes

### Requirement: Click backend is swappable for testing
The cursor backend's click operation SHALL be substitutable the same
way absolute movement already is, so automated tests can assert a click
occurred without a real `uinput` device or OS-level permissions.

#### Scenario: Test suite asserts a click without a real input device
- **WHEN** a test invokes the click operation against a fake backend
- **THEN** the fake backend records that a click occurred, without
  requiring `/dev/uinput` access
