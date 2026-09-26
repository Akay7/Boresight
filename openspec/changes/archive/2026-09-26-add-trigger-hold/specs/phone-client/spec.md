## ADDED Requirements

### Requirement: The on-screen trigger is held while it is pressed
The client SHALL send a trigger `down` message when the trigger control
is pressed and a trigger `up` message when it is released, so holding
the control holds the button and a quick tap is a click. The client
SHALL send `up` for a held trigger whenever the press ends in any other
way: the pointer is cancelled or its capture is lost, the page is
hidden, or streaming stops. The client SHALL NOT send a second `down`
while the trigger is already held, nor an `up` when it is not, and
holding the control SHALL NOT open the browser's long-press menu or
select text.

#### Scenario: Holding the trigger holds the button
- **WHEN** the player presses the trigger, keeps it pressed, and later
  lets go
- **THEN** the client sends one `down` at the press and one `up` at the
  release

#### Scenario: Leaving the page releases the trigger
- **WHEN** the trigger is held and the page is hidden or the pointer is
  cancelled
- **THEN** the client sends `up`

#### Scenario: Stopping releases the trigger
- **WHEN** the trigger is held and streaming is stopped
- **THEN** the client sends `up` before the connection is closed
