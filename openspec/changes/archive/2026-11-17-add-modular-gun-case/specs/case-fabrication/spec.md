# Spec Delta

## Purpose

Defines how the gun case's parts are produced: the rules every part
meets so it prints on a common FDM printer, the fit tuning, what one
build of a configuration outputs, and the automated geometry checks
that keep every shipped configuration printable and assemblable.

## ADDED Requirements

### Requirement: Every part fits the print bed
Every printed part, in its print orientation, SHALL fit the configured
print volume, 180×180×180 mm by default. A build whose part does not fit
SHALL fail, naming the part and its size.

#### Scenario: A small printer
- **WHEN** a configuration sets a 180×180×180 mm print volume
- **THEN** every part of every shipped style and kit fits it

#### Scenario: An oversized remix
- **WHEN** a part is changed so it no longer fits the configured volume
- **THEN** the build fails and reports the part and its dimensions

### Requirement: No part needs support material
Every printed part SHALL print without support material on a 0.4 mm
nozzle in PLA or PETG, in its exported orientation: no downward-facing
surface steeper than 45° from vertical, except bridges no longer than
10 mm and the faces on the bed.

#### Scenario: Slicing with supports off
- **WHEN** any exported part is sliced with supports disabled
- **THEN** the slicer reports no unsupported overhang beyond the allowed
  bridges

#### Scenario: A steep overhang is caught
- **WHEN** a part is changed to have a 60° overhang that is not a bridge
- **THEN** the overhang check fails, naming the part

### Requirement: Parts are exported ready to print
Each part SHALL be exported as STL and 3MF, already in its print
orientation and resting on the bed, so that it needs no rotation in the
slicer.

#### Scenario: Loading a part
- **WHEN** a user drops an exported part into a slicer
- **THEN** it lies flat on the bed in the orientation it was designed to
  print in

### Requirement: Fits come from one clearance setting
Every sliding, clip and peg fit SHALL be derived from one clearance
setting, and every press fit from one interference setting, so that
changing either regenerates every mating feature consistently.

#### Scenario: A printer that prints tight
- **WHEN** a user raises the clearance setting by 0.1 mm and rebuilds
- **THEN** every sliding and peg fit in every part opens by that amount,
  and the parts still pass every check

### Requirement: A fit coupon calibrates the clearance
The build SHALL provide a fit-test coupon carrying the module joint, a
nut trap, a locating peg, the drawer latch and the MX cut-out at a range
of labelled clearances. It SHALL print in under 30 minutes and under
10 g of filament.

#### Scenario: Tuning before the full print
- **WHEN** a user prints the coupon and finds the joint marked 0.25 fits
- **THEN** setting the clearance to 0.25 mm makes every part's fits match
  that joint

### Requirement: Each part states how to print it
The build SHALL list, for every printed part, the material (PETG for the
trigger lever, latches and switch plates, PLA or PETG elsewhere), the
perimeter count and the infill to print it with.

#### Scenario: Reading the print list
- **WHEN** a user opens the print list for a configuration
- **THEN** each part has its material, perimeters and infill next to it

### Requirement: One command builds a configuration
One command SHALL take a configuration (board kit, power drawer, trigger
mechanism, switch plate, style, style parameters, print volume and
clearances) and output every part's STL and 3MF, a STEP file of each part
and of the assembly, the skin interface, a bill of materials and an
exploded-view drawing.

#### Scenario: Building a Pi gun
- **WHEN** the command is run with the Pi kit, the USB tether, the
  filament-pin lever with the MX plate and the `minimal` style
- **THEN** the output directory holds every part needed for that gun and
  no part it does not need, plus the STEP files, interface, bill of
  materials and drawing

#### Scenario: Building every configuration
- **WHEN** the command is run for every shipped configuration at once
- **THEN** each distinct part is written once, and each configuration
  gets its own bill of materials, naming the part files to print, and
  its own drawing

### Requirement: The bill of materials covers everything to buy
The bill of materials SHALL list every printed part with its count, and
every purchased part with its count and specification: screws by size
and length, nuts, the spring, connectors, the regulator, the switches,
battery holders or modules, and cables.

#### Scenario: Shopping for an AA ESP32-CAM gun
- **WHEN** a user buys exactly what the bill of materials lists for that
  configuration
- **THEN** they have every part needed to assemble the gun, and no
  screw left over

### Requirement: Assemblies are checked for interference
For every valid shipped configuration, an automated check SHALL confirm
that no two printed parts overlap except at declared press fits, and
that every purchased part (boards, camera, cells, holders, regulator,
switches, connectors, screws, nuts) fits its pocket without overlapping
printed material.

#### Scenario: A pocket too small for the regulator
- **WHEN** the regulator's pocket is made smaller than the regulator
- **THEN** the check fails, naming the regulator and the part it
  overlaps

### Requirement: The camera's view is checked
For each camera a kit supports, an automated check SHALL confirm that
its field of view, from the lens out past the muzzle, is clear of every
printed part of every shipped style.

#### Scenario: A muzzle lip in the frame
- **WHEN** a style's muzzle is changed so its lip enters the camera's
  field of view
- **THEN** the check fails, naming the style, the part and the camera

### Requirement: Ready-to-print files are published by CI
Generated meshes SHALL NOT be committed. CI SHALL build every valid
shipped configuration on each run and publish one downloadable artifact
holding every distinct part once (STL, 3MF and STEP) and each
configuration's bill of materials and drawing, so a builder can print
without installing the CAD toolchain.

#### Scenario: Printing without Python
- **WHEN** a user downloads the artifact from a CI run and opens their
  configuration's bill of materials
- **THEN** every part file it lists is in the artifact, with the drawing,
  without running the build themselves
