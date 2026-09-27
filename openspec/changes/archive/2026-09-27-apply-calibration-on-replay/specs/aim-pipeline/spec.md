## ADDED Requirements

### Requirement: Replay applies a sequence's own calibration
The replay entry point SHALL, when a replayed sequence's manifest carries
a lens model or a zero for the session it was recorded from, apply them
to every replayed frame exactly as the live session did: the lens only to
frames of the image size it was calibrated at, the zero to every frame.
It SHALL offer a way to replay without them. A stored lens or zero that
cannot be read SHALL be reported and left out, not fail the replay.

#### Scenario: A zeroed recording replays to the zeroed aim
- **WHEN** a sequence whose manifest carries a zero is replayed
- **THEN** each solved frame's aim equals what the per-frame operation
  gives that frame with that zero

#### Scenario: A calibrated recording replays with its lens
- **WHEN** a sequence whose manifest carries a lens model for its frame
  size is replayed
- **THEN** each frame is solved with that lens applied

#### Scenario: A lens for another frame size is not applied
- **WHEN** the stored lens model's image size differs from the frames'
- **THEN** the frames are solved without it

#### Scenario: Calibration can be turned off
- **WHEN** a sequence carrying a lens and a zero is replayed with
  calibration turned off
- **THEN** the track equals replaying the same frames with neither

#### Scenario: Fixtures without calibration are unchanged
- **WHEN** a sequence whose manifest carries no recording block is
  replayed
- **THEN** the track is the same as before this change
