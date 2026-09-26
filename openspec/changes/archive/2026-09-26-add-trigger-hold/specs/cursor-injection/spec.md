## ADDED Requirements

### Requirement: The cursor backend can hold and release the primary button
The cursor backend interface SHALL expose press and release operations,
distinct from click, that respectively press and release the primary
button at the cursor's current position without moving it. Absolute
movement between a press and a release SHALL move the cursor with the
button held. A click SHALL be equivalent to a press immediately followed
by a release. On Linux the button SHALL be the same one a click uses,
so a hold and a click land on the same pointer as the cursor movement.
Closing the backend SHALL release a button still held.

#### Scenario: A press, a move and a release are a drag
- **WHEN** press is invoked, then absolute movement to a new position,
  then release
- **THEN** the OS observes the button going down at the old position,
  the cursor moving with it held, and the button going up at the new
  position

#### Scenario: Closing releases a held button
- **WHEN** the backend is closed while the button is held
- **THEN** the OS observes the button released

#### Scenario: A fake backend records holds
- **WHEN** a test presses and releases against a fake backend
- **THEN** the fake records the press and the release, without
  `/dev/uinput` access
