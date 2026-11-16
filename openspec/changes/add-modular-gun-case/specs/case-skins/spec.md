# Spec Delta

## Purpose

Defines how the gun case's appearance is changed: skins are a separate
layer over the functional core, attached and bounded by a published
interface, so a gun can be restyled, or a new style designed in any CAD
tool, without touching its structure or electronics.

## ADDED Requirements

### Requirement: Restyling replaces only skin parts
A gun's appearance SHALL be set by its skin parts alone. Changing to
another style SHALL replace only skin parts, and SHALL NOT require
removing the board, camera, cells, trigger cassette or any wiring.

#### Scenario: Changing style on an assembled gun
- **WHEN** a user swaps a gun's skins for another style
- **THEN** they remove and fit only skin parts and their screws, and the
  electronics and core modules stay in place

### Requirement: Skins attach only at the attachment points
Skin parts SHALL attach to the core only at the attachment points the
skin interface publishes, with the case's M3 screws, and SHALL rest only
on the core's outer surface, never on a functional part.

#### Scenario: A skin's screws line up
- **WHEN** a skin part built to the interface is placed on the core
- **THEN** each of its screw holes lines up with an attachment point and
  it is held with the case's own screws

### Requirement: Skins stay out of the keep-out zones
No skin part SHALL enter a keep-out zone: the camera's field of view,
the vents, the trigger's travel and the finger's path to it, the power
drawer's path and latch, the power switch, the USB-C charge port and its
indicator, the cable exit and the status LED windows.

#### Scenario: A long barrel shroud
- **WHEN** a style's barrel shroud is lengthened past the camera
- **THEN** its opening widens with the field of view, or the check fails
  naming the field-of-view zone

#### Scenario: Battery swap with skins on
- **WHEN** a skinned gun's drawer is changed
- **THEN** no skin part is in the way of the latch or the drawer

### Requirement: Every shipped style fits every valid configuration
Each shipped style SHALL fit every valid configuration: both board kits,
every power drawer, every trigger mechanism and both switch plates,
without a kit-specific skin part.

#### Scenario: One skin set, two boards
- **WHEN** a gun built with a style's skins is converted from the
  ESP32-CAM kit to the Pi kit
- **THEN** the same skin parts fit and leave both kits' LED windows and
  vents open

### Requirement: Two original styles ship
The case SHALL ship two skin styles, `minimal` and `blaster`, each an
original design and not a replica of any commercial product.

#### Scenario: Choosing a style
- **WHEN** a configuration names `minimal` or `blaster`
- **THEN** the build produces that style's full set of skin parts

### Requirement: Styles are parametric
Each style SHALL expose its shape options (for example barrel shroud
length, edge chamfer, grip texture) as named parameters with stated
ranges. Any value within a parameter's range SHALL produce skins that
pass every check.

#### Scenario: A value out of range
- **WHEN** a configuration sets a style parameter outside its range
- **THEN** the build refuses and names the parameter and its range

### Requirement: Styles can be printed in several colours on any printer
Each style SHALL split its decorative details into separate parts that
attach to the main skin parts, so a style can be printed in two or more
colours on a single-filament printer.

#### Scenario: A two-colour gun
- **WHEN** a user prints the main skins in one filament and the accent
  parts in another
- **THEN** the accent parts fit their skin parts without glue

### Requirement: The skin interface is published
Every build SHALL output the skin interface for its configuration in
formats any CAD tool can import: the core's outer envelope, each
attachment point's position and axis, and each keep-out zone as a named
solid.

#### Scenario: Designing a skin in another CAD tool
- **WHEN** a designer imports the interface files into their CAD tool
- **THEN** they can see the core's envelope, every attachment point and
  every keep-out zone by name

### Requirement: A third-party skin can be checked
A command SHALL check skin parts supplied as STL or 3MF against the skin
interface: that each stays out of the core envelope and every keep-out
zone, has a clear screw hole on each attachment point it covers, and
fits the print bed. It SHALL report each violation with the part and the
zone or attachment point.

#### Scenario: A skin that blocks a vent
- **WHEN** a third-party skin part covers the Pi's vent openings
- **THEN** the check fails, naming the part and the vent zone

#### Scenario: A conforming skin
- **WHEN** a third-party skin meets every rule
- **THEN** the check passes and reports each part as conforming
