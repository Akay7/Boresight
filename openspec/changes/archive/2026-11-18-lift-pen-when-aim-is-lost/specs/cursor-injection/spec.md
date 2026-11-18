## ADDED Requirements

### Requirement: The Linux pen hovers only while something aims
On Linux the cursor device SHALL be a pen that is in proximity only
while something aims. It SHALL enter proximity with the first move after
being out of it, in the same event frame as that move's position, and
SHALL leave proximity when told that nothing is aiming, unless its tip
is held down, in which case it SHALL stay until the tip is released and
it is told again.

#### Scenario: Losing the aim takes the pen away
- **WHEN** the pen is hovering with its tip up and the backend is told
  nothing is aiming
- **THEN** the pen leaves proximity, and the next move brings it back at
  that move's position with no further out-and-in pair

#### Scenario: A held tip keeps the pen in proximity
- **WHEN** the backend is told nothing is aiming while the tip is held
  down
- **THEN** the pen stays in proximity, and after the tip is released the
  next such call takes it out

#### Scenario: Closing lifts the pen
- **WHEN** the backend closes while the pen hovers, with or without the
  tip held
- **THEN** a held tip is lifted and the pen leaves proximity

### Requirement: The pen turns off libinput's forced proximity out
The first time the Linux pen enters proximity it SHALL also leave and
re-enter it once. libinput forces out of proximity, 50 ms after its last
event, any pen that has not yet sent a proximity out of its own, and
forces it back in with the next event; one real proximity out switches
that off for the device.

#### Scenario: The cursor does not blink between slow frames
- **WHEN** the pen first enters proximity
- **THEN** it writes proximity in, out and in again, so libinput stops
  forcing it out between frames that arrive more than 50 ms apart

### Requirement: Nothing is clicked while nothing aims
The cursor backend SHALL put the tip down for a press or click only
while the pen is in proximity. A press, click or release while it is out
of proximity SHALL write no button events, so a trigger pulled after
the aim was lost clicks nowhere rather than at the last aimed position.
On Windows, macOS and the USB HID gun, being told that nothing is aiming
SHALL do nothing: their cursor stays where it was last put.

#### Scenario: A trigger with nothing aiming clicks nowhere
- **WHEN** the pen has left proximity and a click, press or release is
  requested
- **THEN** no tip events are written
