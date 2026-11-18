# Spec Delta

## ADDED Requirements

### Requirement: Bolts are checked against what works
For every valid shipped configuration, an automated check SHALL confirm
that no bolt or nut crosses a module, a lead's path or a camera's field
of view, and that no metal part lies within 10 mm of the ESP32-CAM's or
the Pi Zero 2 W's PCB antenna.

#### Scenario: A bolt moved into the antenna's zone
- **WHEN** the muzzle port's bolts are moved within 10 mm of the
  ESP32-CAM's antenna
- **THEN** the check fails, naming the bolt, the board and the antenna
  zone

#### Scenario: A bolt across the Pi's sled
- **WHEN** a port bolt is placed where it crosses the Pi sled
- **THEN** the check fails, naming the bolt and the sled

## MODIFIED Requirements

### Requirement: One command builds a configuration
One command SHALL take a configuration and output every part's STL and
3MF, a STEP file of each part and of the assembly, the skin interface, a
bill of materials and an exploded-view drawing. A configuration names the
board kit, power drawer, trigger mechanism, switch plate, number of
barrels, feedback device, buttons, style, style parameters, print volume
and clearances.

#### Scenario: Building a Pi gun
- **WHEN** the command is run with the Pi kit, the 18650 drawer, one
  barrel, the bolt lever with the MX plate, the solenoid, the buttons and
  the `minimal` style
- **THEN** the output directory holds every part needed for that gun and
  no part it does not need, including the solenoid carrier, the cable
  clamp and the button panel, plus the STEP files, interface, bill of
  materials and drawing

#### Scenario: Building every configuration
- **WHEN** the command is run for every shipped configuration at once
- **THEN** each distinct part is written once, and each configuration
  gets its own bill of materials, naming the part files to print, and
  its own drawing

### Requirement: The bill of materials covers everything to buy
The bill of materials SHALL list every printed part with its count, and
every purchased part with its count and specification:
- bolts by size and length, lock nuts, and the drawer's thumbscrew;
- the spring, the regulator, the switches and LEDs;
- the hub's perfboard and sockets;
- battery holders or modules;
- the feedback device and its driver;
- every lead, with its plug type, the header pins it plugs onto and its
  length;
- cables.

#### Scenario: Shopping for an AA ESP32-CAM gun
- **WHEN** a user buys exactly what the bill of materials lists for that
  configuration
- **THEN** they have every part needed to assemble the gun, and no bolt
  or nut left over

#### Scenario: Wiring the LRA
- **WHEN** a builder wires the LRA carrier on a Pi gun from the bill of
  materials alone
- **THEN** it names the lead's plug, the hub socket it goes to, and the
  header pins (1, 3, 5) the hub's Pi lead uses for 3.3 V and I2C1

### Requirement: Assemblies are checked for interference
For every valid shipped configuration, an automated check SHALL confirm
that no two printed parts overlap except at declared press fits. Every
purchased part SHALL fit its pocket without overlapping printed material:
- boards, camera, cells and holders;
- the hub's parts, switches and connectors;
- bolts, nuts and crush tubes;
- the feedback device;
- the plugs at the Pi's window.

#### Scenario: A pocket too small for the regulator
- **WHEN** the hub's regulator pocket is made smaller than the regulator
- **THEN** the check fails, naming the regulator and the part it
  overlaps

#### Scenario: A plug that cannot reach the Pi
- **WHEN** the barrel's window is made too short for the right-angle
  HDMI plug
- **THEN** the check fails, naming the plug, the barrel and the window
