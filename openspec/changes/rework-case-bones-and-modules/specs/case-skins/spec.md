# Spec Delta

## MODIFIED Requirements

### Requirement: Restyling replaces only skin parts
A gun's appearance SHALL be set by its skin parts (covers) alone.
Changing to another style SHALL replace only skin parts. It SHALL NOT
require removing the board, camera, cells, trigger module, hub or any
wiring, or pulling the bones apart.

#### Scenario: Changing style on an assembled gun
- **WHEN** a user swaps a gun's covers for another style
- **THEN** they take out and refit only the through-bolts and the cover
  parts, one bone at a time, while the tenons keep the bones joined and
  the electronics and modules stay in place

### Requirement: Skins attach only at the attachment points
Skin parts SHALL be held only by the gun's through-bolts, at the bolt
positions the skin interface publishes. Each SHALL carry a clear hole and,
on the right side, a hex pocket for the nut. No skin part SHALL use a
hook, snap or slide of its own, and skins SHALL rest only on the bones'
outer surfaces, never on a functional part.

#### Scenario: A skin's screws line up
- **WHEN** a skin part built to the interface is placed on the bones
- **THEN** each of its holes lines up with a through-bolt position, and
  it is clamped by the gun's own bolts and nuts

#### Scenario: A skin with a hook
- **WHEN** a style adds a hook or snap that holds a skin part on
- **THEN** the skin check fails, naming the part

### Requirement: Skins stay out of the keep-out zones
No skin part SHALL enter a keep-out zone:
- the camera's field of view;
- the vents;
- the trigger's travel and the finger's path to it;
- the power drawer's path and its thumbscrew;
- the power switch, the Start and Select buttons and the LED windows;
- the USB-C charge port and its indicator;
- the Pi's window, its plugs and the cable clamp;
- the ESP32-CAM nose's debug socket and BOOT button;
- the 10 mm zone around each board's antenna, for any metal or
  metal-filled part.

#### Scenario: A long barrel shroud
- **WHEN** a style's barrel shroud is lengthened past the camera
- **THEN** its opening widens with the field of view, or the check fails
  naming the field-of-view zone

#### Scenario: Battery swap with skins on
- **WHEN** a covered gun's drawer is changed
- **THEN** no cover is in the way of the thumbscrew or the drawer

#### Scenario: Plugging HDMI with covers on
- **WHEN** a covered Pi gun is plugged into a TV
- **THEN** no cover is in the way of the plug at the window

### Requirement: Every shipped style fits every valid configuration
Each shipped style SHALL fit every valid configuration without a
kit-specific skin part, where any variant only adds or closes openings:
- both board kits;
- every power drawer;
- both trigger mechanisms and both switch plates;
- zero, one or two barrels;
- every feedback device;
- with or without the buttons.

#### Scenario: One skin set, two boards
- **WHEN** a gun built with a style's covers is converted from the
  ESP32-CAM kit to the Pi kit
- **THEN** the same receiver, grip and barrel covers fit, and the
  barrel's lower cover leaves the Pi's window open

#### Scenario: Adding a second barrel
- **WHEN** a second barrel is added to a covered gun
- **THEN** a second set of the style's barrel covers fits it on the same
  bolt positions

### Requirement: Styles can be printed in several colours on any printer
Each style SHALL split its decorative details into separate parts, so a
style can be printed in two or more colours on a single-filament printer.
Each accent part SHALL be clamped under a through-bolt or captured
between a cover and a bone. None SHALL need glue.

#### Scenario: A two-colour gun
- **WHEN** a user prints the main covers in one filament and the accent
  parts in another
- **THEN** the accent parts are held by the gun's own bolts or trapped by
  a cover, without glue

### Requirement: The skin interface is published
Every build SHALL output the skin interface for its configuration in
formats any CAD tool can import:
- the bones' outer envelope;
- each through-bolt's position and axis, with the clamp thickness a cover
  flange must have there;
- each keep-out zone as a named solid.

#### Scenario: Designing a skin in another CAD tool
- **WHEN** a designer imports the interface files into their CAD tool
- **THEN** they can see the envelope, every bolt position with its flange
  thickness, and every keep-out zone by name

### Requirement: A third-party skin can be checked
A command SHALL check skin parts supplied as STL or 3MF against the skin
interface. Each part SHALL stay out of the envelope and every keep-out
zone, have a clear hole of the right flange thickness on each bolt
position it covers, and fit the print bed. The command SHALL report each
violation with the part and the zone or bolt position.

#### Scenario: A skin that blocks a vent
- **WHEN** a third-party skin part covers the Pi's vent openings
- **THEN** the check fails, naming the part and the vent zone

#### Scenario: A conforming skin
- **WHEN** a third-party skin meets every rule
- **THEN** the check passes and reports each part as conforming
