# Spec Delta

## Purpose

Lets the gun aim at the display its own computer drives, such as a
Raspberry Pi plugged into a TV, next to a game or emulator Boresight does
not own, using the same overlay, cursor and pipeline as a PC with a
phone.

## ADDED Requirements

### Requirement: The gun's output is chosen in its configuration
The gun SHALL read `output` from its configuration file: `usb` for the
USB absolute mouse, or `local` for the Pi's own display. Without
`output`, it SHALL use `usb`. Any other value SHALL stop it at startup,
with an error naming both accepted values.

#### Scenario: No output keeps today's behaviour
- **WHEN** the configuration file has no `output`
- **THEN** the gun starts as a USB mouse exactly as before

#### Scenario: An unknown output is refused
- **WHEN** `output` is any value other than `usb` or `local`
- **THEN** the gun exits at startup with an error naming `usb` and `local`

### Requirement: The local output moves the Pi's own cursor
With the `local` output, the gun SHALL deliver its aim to the Pi's
display through the same Linux absolute-pointer device the server uses,
so any program on that display reads it as a pointer. The trigger SHALL
hold the primary button while it is pressed, as in USB mode.

#### Scenario: Aiming moves the cursor
- **WHEN** the gun solves an aim at a point on the Pi's display
- **THEN** the cursor moves to that point

#### Scenario: The trigger is the primary button
- **WHEN** the trigger is pressed and released, with contact bounce
- **THEN** programs on the display see exactly one primary-button press
  and one release, at the aim point

#### Scenario: No pointer device is explained
- **WHEN** the gun cannot create the pointer device, for example without
  permission for `/dev/uinput`
- **THEN** it exits at startup with an error naming the device and the
  missing permission

### Requirement: The local output draws its markers with the existing overlay
With the `local` output, the gun SHALL show its markers through the same
on-screen overlay the server uses, on the Pi's display. It SHALL solve
against the layout that overlay reports for the geometry it actually
drew, exactly as the server does, so the drawn and solved layouts cannot
differ. Any `layout` file in the configuration SHALL be ignored, and the
gun SHALL log that it was ignored.

#### Scenario: Drawn and solved layouts agree
- **WHEN** the local output starts and the overlay reports its geometry
- **THEN** the gun solves against the layout derived from that geometry

#### Scenario: The overlay cannot run
- **WHEN** the overlay refuses to start, for example with no desktop
  session
- **THEN** the gun exits with the overlay's explanation and does not move
  the cursor

#### Scenario: The overlay dies while running
- **WHEN** the overlay process exits while the gun is running
- **THEN** the gun stops aiming, releases a held button, logs the
  overlay's last output and exits with a failure

### Requirement: The overlay settings match the server's
The local output SHALL accept the same overlay settings the server does:
- the extra margin
- the display to draw on
- the side-bar placement's picture aspect

Each SHALL mean the same thing in both places.

#### Scenario: A margin for an overscanning TV
- **WHEN** `[overlay] extra_margin_px` is set
- **THEN** the overlay shrinks its area by that many pixels on every side,
  as the server's setting of the same name does

#### Scenario: Tags beside a 4:3 emulator picture
- **WHEN** `[overlay] picture_aspect` is `4:3`
- **THEN** the tags are placed in the bars beside a centred 4:3 picture

### Requirement: The gun can start with the user's desktop session
`boresight-gun --autostart` SHALL write a desktop autostart entry for the
current user, without root, that starts the gun with the same
configuration when that user's desktop session starts. The entry SHALL
restart the gun after it fails and SHALL NOT restart it after a clean
exit. `--autostart remove` SHALL delete the entry.

#### Scenario: Login to aiming
- **WHEN** the entry is written and the user's desktop session starts
- **THEN** the gun starts with the configuration it was written with,
  with no command

#### Scenario: A failed gun is restarted
- **WHEN** the gun started by the entry exits with a failure
- **THEN** it is started again after a short pause

#### Scenario: Removing the entry
- **WHEN** `boresight-gun --autostart remove` runs
- **THEN** the entry is gone and nothing else is changed

### Requirement: The local output runs without a Pi
The gun SHALL run the `local` output on an ordinary computer with
recorded frames, a recording cursor and an overlay layout supplied by
the test. Its aim and button events SHALL then be checkable with no
camera, GPIO, display or uinput device.

#### Scenario: Recorded frames move the recording cursor
- **WHEN** the local output runs emulated on recorded frames whose aim is
  known
- **THEN** the recorded cursor positions equal the aim the pipeline
  solves for those frames against that layout
