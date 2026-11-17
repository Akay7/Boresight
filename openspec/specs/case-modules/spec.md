# case-modules Specification

## Purpose

Defines the printable gun case's mechanical and electrical architecture:
the core modules and how they join, the interchangeable board kits,
power drawers and trigger switches, which combinations are valid, and
how the gun comes apart and goes back together.

## Requirements

### Requirement: The core is a set of modules with one joint type
The case's structure SHALL be these modules: receiver, barrel, grip,
rear cap, trigger cassette, camera bulkhead, board sled and power
drawer. The barrel, grip and rear cap SHALL each join the receiver
through the same joint type, held by a single M3 screw, so a
replacement module of any shape fits if it carries that joint.

#### Scenario: A remixed barrel fits an existing receiver
- **WHEN** a barrel of a different shape is built with the standard joint
- **THEN** it seats in the receiver and is held by one M3 screw, with no
  change to the receiver

#### Scenario: Each structural joint takes one screw
- **WHEN** the barrel, grip or rear cap is fitted to the receiver
- **THEN** one M3 screw secures it and no other fastener is needed

### Requirement: The core alone is a working gun
Every functional part (board, camera, cells, regulator, switches,
trigger lever, LED, wiring) SHALL be held by core modules. A gun
assembled with no skin parts fitted SHALL aim and fire as it does with
skins.

#### Scenario: Bench test without skins
- **WHEN** a gun is assembled with its core modules and no skins
- **THEN** every functional part is held in place, and the gun aims and
  its trigger works

### Requirement: One core takes either board
The core SHALL accept an ESP32-CAM kit or a Raspberry Pi Zero 2 W kit.
Switching between them SHALL replace only the board kit's parts and the
power drawer; the receiver, barrel, grip, rear cap, trigger cassette
and skins SHALL be shared by both.

#### Scenario: Converting an ESP32-CAM gun to a Pi gun
- **WHEN** a builder converts an assembled ESP32-CAM gun to the Pi kit
- **THEN** they replace the camera bulkhead, add the Pi sled and fit the
  USB tether drawer, and reuse every other part

### Requirement: The ESP32-CAM kit
The ESP32-CAM kit SHALL hold an AI-Thinker ESP32-CAM on the camera
bulkhead with its camera facing forward along the barrel axis, its
header pins reachable for plug-on leads, a place for a 470–1000 µF
capacitor across 5 V and GND at the board, and no metal part within
10 mm of the board's PCB antenna.

#### Scenario: Flashing without unsoldering
- **WHEN** the builder needs to reflash the ESP32-CAM
- **THEN** they remove the bulkhead, unplug the leads from the header,
  and reach every header pin with the board still on the bulkhead

#### Scenario: Antenna clearance
- **WHEN** the ESP32-CAM kit is assembled in any valid configuration
- **THEN** no screw, nut, cell or other metal part lies within 10 mm of
  the PCB antenna

### Requirement: The Pi Zero 2 W kit
The Pi kit SHALL hold a Raspberry Pi Camera Module 2 or 3 on the camera
bulkhead and the Pi Zero 2 W on a sled in the receiver, joined by a Pi
Zero camera ribbon. The Pi's micro-SD card SHALL be removable after
taking off only the rear cap.

#### Scenario: Either camera module fits
- **WHEN** the Pi camera bulkhead is fitted with a Camera Module 2 or a
  Camera Module 3
- **THEN** the camera is held on the same mounting points and faces
  forward along the barrel axis

#### Scenario: Swapping the SD card
- **WHEN** the builder removes the rear cap of an assembled Pi gun
- **THEN** the micro-SD card can be pulled and reinserted without
  removing the sled, the skins or any other module

### Requirement: The Pi's USB cable is anchored at the grip base
In the Pi kit, the USB cable to the host SHALL exit through the grip
base, and a strain relief in the case SHALL take any pull on the cable
so that it does not reach the Pi's connector.

#### Scenario: A tug on the cable
- **WHEN** the cable is pulled hard at the grip base
- **THEN** the strain relief holds and the plug at the Pi stays seated

### Requirement: The Pi has room to cool
The case SHALL provide vent openings over the Pi's processor and room
for a heatsink up to 14×14×6 mm on it. With the heatsink fitted, the
processor's temperature in the closed case SHALL stay within 10 °C of
the same board running the same load in open air.

#### Scenario: Temperature after a long session
- **WHEN** the Pi gun runs the aim pipeline for 30 minutes in the closed
  case, and again as a bare board in open air at the same room temperature
- **THEN** the in-case processor temperature is at most 10 °C higher

### Requirement: The camera holds its aim
The camera SHALL be located by positive features of the core (keys,
pegs or slots), never by friction alone, and no skin part SHALL touch
the camera, its bulkhead or the board holding it, so that fitting or
swapping skins never moves the camera.

#### Scenario: Restyling keeps the zero
- **WHEN** a zeroed gun's skins are replaced with another style
- **THEN** the aim point is unchanged and no re-zeroing is needed

### Requirement: The camera sees out unobstructed
The muzzle aperture SHALL clear the fitted camera's full field of view,
and the camera's lens SHALL sit in a light-tight aperture so that no
light from inside the case (LEDs, light guides) reaches it.

#### Scenario: No vignetting
- **WHEN** a frame is captured through the assembled muzzle
- **THEN** no part of the case appears in any corner of the frame

### Requirement: Interchangeable power drawers
The grip SHALL take one of four power drawers through the same bay: 4×AA,
4×AAA, one 18650 cell, or a USB tether. Each drawer SHALL be keyed so it
can only be inserted the right way round.

#### Scenario: Changing battery type
- **WHEN** a builder replaces the AA drawer with the 18650 drawer
- **THEN** the new drawer slides into the same bay and latches, with no
  other part changed

#### Scenario: A reversed drawer does not go in
- **WHEN** a drawer is offered to the bay the wrong way round
- **THEN** it does not enter far enough to make electrical contact

### Requirement: Batteries swap without tools
A battery drawer SHALL come out and go back in by hand, with no tool, no
skin or other part removed, and no wire unplugged: it SHALL make its
electrical connection when it latches.

#### Scenario: Swapping AA cells
- **WHEN** the AA cells run flat
- **THEN** the user releases the latch, pulls the drawer, changes the
  cells, pushes it back until it latches, and the gun powers up

### Requirement: The board gets a steady 5 V from any battery drawer
Every battery drawer SHALL feed one regulator that supplies
the board 4.75–5.25 V at up to 1 A across the drawer's whole usable cell
voltage range, alkaline or NiMH for AA and AAA.

#### Scenario: Nearly flat NiMH cells
- **WHEN** four NiMH AA cells have discharged to 1.0 V each and the
  ESP32-CAM is streaming
- **THEN** the board still receives 4.75–5.25 V

### Requirement: One switch turns a battery gun on and off
A battery-powered gun SHALL have one power switch, in the path from the
drawer to the regulator, that can be operated with the skins fitted.

#### Scenario: Switching off
- **WHEN** the user moves the power switch to off
- **THEN** the regulator and the board draw no current from the cells

### Requirement: The 18650 drawer charges in place and is protected
The 18650 drawer SHALL charge its cell through a USB-C port reachable at
the grip base with the drawer installed, show charge status through the
case, and protect the cell against over-discharge, over-current and
short circuit.

#### Scenario: Charging overnight
- **WHEN** a USB-C charger is plugged into the grip base with the power
  switch off
- **THEN** the cell charges and the charging indicator is visible from
  outside the case

#### Scenario: Running the cell down
- **WHEN** the gun is left on until the cell reaches its protection
  cut-off voltage
- **THEN** the cell is disconnected from the load

### Requirement: Valid configurations
A configuration SHALL name a board kit, a power drawer, a trigger
mechanism, a trigger switch plate and a skin style. The ESP32-CAM kit
SHALL accept any of the four drawers; the Pi kit SHALL accept only the
USB tether, since its USB cable is both its power and its data. Every
mechanism SHALL accept either switch plate with either kit.

#### Scenario: A Pi with batteries is refused
- **WHEN** a configuration pairs the Pi kit with a battery drawer
- **THEN** the build refuses before generating any part, and names the
  board, the drawer and the reason

#### Scenario: An ESP32-CAM on the tether
- **WHEN** a configuration pairs the ESP32-CAM kit with the USB tether
- **THEN** the build succeeds and the board is powered from the cable

### Requirement: The trigger's mechanism is swappable
The trigger SHALL be one of three mechanisms on the same mount (the
receiver's rails, one screw and the trigger plug): a lever turning on a
1.75 mm filament pin, a lever turning on an M3 bolt, or a push button
pressed straight back. Changing mechanism SHALL replace only that
mechanism's printed parts and pivot; the switch plates, the switch and
the lead to the board SHALL be the same for every mechanism.

#### Scenario: Changing from the filament pin to a bolt
- **WHEN** a builder replaces the filament-pin cassette and lever with
  the bolt cassette and lever
- **THEN** the switch plate, switch and lead are reused, the cassette is
  held by the same one screw, and the trigger works

#### Scenario: A button instead of a lever
- **WHEN** the button cassette is fitted with the MX plate
- **THEN** pressing the button actuates the switch, the button moving as
  far as the switch does

### Requirement: The trigger takes a keyboard switch or a lever microswitch
Every trigger mechanism SHALL take an interchangeable switch plate: one for
any plate-mount switch with the MX footprint (14 mm square cut-out), one
for a 20×10×6 mm lever microswitch with two mounting holes 9.5 mm apart.
Changing the switch type SHALL replace only the switch plate.

#### Scenario: Fitting an MX-style switch
- **WHEN** an MX-footprint switch is snapped into its plate and the plate
  is fitted to the cassette
- **THEN** pulling the trigger actuates the switch

#### Scenario: Changing to a microswitch
- **WHEN** the MX plate is replaced with the microswitch plate
- **THEN** the mechanism's parts and the lead to the board are
  unchanged, and the trigger works

### Requirement: The trigger never bottoms out the switch
Every trigger mechanism SHALL have an over-travel stop, adjustable with
the case's hex key, that halts the trigger (lever or button) after the
switch actuates and before the switch reaches its mechanical end of
travel.

#### Scenario: A hard pull
- **WHEN** the trigger is pulled or pressed fully and hard, with any
  mechanism and either switch plate
- **THEN** the switch has actuated and the trigger, not the switch,
  takes the force at the stop

### Requirement: The trigger returns by itself
The trigger SHALL return to rest unassisted after release with any
mechanism and either switch plate, by a spring held in the cassette, so
that release is registered on every pull.

#### Scenario: Release with a light microswitch
- **WHEN** the trigger is released with the microswitch plate fitted
- **THEN** the lever or button returns to rest and the switch releases

### Requirement: The trigger and LED use the existing pins
The trigger SHALL be wired between the board's trigger input and GND
on the pins the existing software defaults to: GPIO13 on the
ESP32-CAM, and GPIO17 (header pin 11) on the Pi. The Pi kit's status
LED SHALL be wired to GPIO27 (header pin 13).

#### Scenario: No software change
- **WHEN** a case is built with either kit and the board runs its
  existing default configuration
- **THEN** the trigger and the status LED work without editing any
  setting

### Requirement: The status LED is visible in use
The board's status LED SHALL be visible from the shooter's position with
skins fitted: the ESP32-CAM kit SHALL carry the on-board LED's light to a
window through a light guide, and the Pi kit SHALL mount its LED in the
rear cap.

#### Scenario: Checking the solve state while aiming
- **WHEN** the user holds the assembled gun aimed at the screen
- **THEN** they can see the status LED's pattern without turning the gun

### Requirement: Every connection between modules is a plug
Every electrical connection that crosses a module boundary SHALL be a
polarized plug and socket. No soldered joint SHALL cross a module
boundary, and the case SHALL need no custom circuit board, only
off-the-shelf modules and wires.

#### Scenario: Removing the trigger cassette
- **WHEN** the trigger cassette is taken out
- **THEN** its lead unplugs from the board side, and no wire needs
  cutting or desoldering

### Requirement: The gun comes apart with one hex key
Taking the gun fully apart, to separate modules and unplugged
electronics, SHALL need only a 2.5 mm hex key and at most 12 screws, all
M3 socket-head in at most two lengths. Screws a teardown leaves in place
inside a module, such as the trigger's pivot bolt and stop screw, do not
count. No glue, cutting or desoldering SHALL be needed, and reassembly
SHALL be the same steps reversed.

#### Scenario: A full teardown and rebuild
- **WHEN** a builder takes an assembled gun apart and rebuilds it
- **THEN** they used only the hex key, removed at most 12 screws, and
  the rebuilt gun works as before

### Requirement: Screws never thread into plastic
Every screw SHALL engage a captive metal nut or a heat-set insert, never
a thread formed in the printed part, so repeated assembly does not wear
the joints.

#### Scenario: Twenty rebuilds
- **WHEN** the gun has been taken apart and rebuilt 20 times
- **THEN** every joint still tightens fully and none has worked loose
