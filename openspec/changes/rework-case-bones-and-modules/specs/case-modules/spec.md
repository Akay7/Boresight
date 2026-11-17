# Spec Delta

## ADDED Requirements

### Requirement: Only steel holds the gun together
Every joint between bones, every module and every cover SHALL be held by
steel fasteners passing through the plastic: M3 bolts with nuts, or a
captive thumbscrew. No printed hook, slide rail, snap fit or flexing latch
SHALL hold any part in place, so that a printed feature never carries the
load that keeps a part on the gun.

#### Scenario: A drop onto a hard floor
- **WHEN** an assembled gun, printed in PLA, is dropped from 1.5 m onto a
  hard floor on its muzzle, its side and its grip base
- **THEN** no bone, module, cover or drawer has come off or loosened

#### Scenario: Inspecting the parts
- **WHEN** every printed part of every shipped configuration is examined
- **THEN** none relies on bending a printed feature to hold another part

### Requirement: Port bolts pass straight through the gun
Each port SHALL be held by two M3 bolts, 6 mm in from its mouth, at
z = +12 and z = −12 mm. Each SHALL pass through the left cover, both bone
walls, the tenon or module inside and the right cover, and SHALL take a
nylon-insert nut sunk in the right cover. A printed crush tube between
the walls SHALL keep the bolt from squeezing the bone.

#### Scenario: One bolt does three jobs
- **WHEN** the barrel is joined to the receiver with covers fitted
- **THEN** the two port bolts hold the barrel, the receiver's covers and
  the barrel's covers, with no other fastener

### Requirement: The grip is held by two through-bolts
The grip SHALL be held to the receiver by one through-bolt across its
joint, and its covers SHALL be clamped at the bottom by a second
through-bolt in a boss on the grip's back, below the drawer bay. Neither
SHALL cross the drawer bay.

#### Scenario: Changing the drawer leaves the grip tight
- **WHEN** the drawer is taken out
- **THEN** the grip and its covers stay held by their two bolts

### Requirement: The barrel repeats
A gun SHALL have no barrel, one barrel or two barrels, every barrel the
same printed part. A barrel SHALL fit any port by its tenon, so a second
barrel goes on the first one's muzzle port, and the camera module moves
to the new end.

#### Scenario: From standard to long
- **WHEN** a builder adds a second barrel to a standard gun
- **THEN** they move the camera module to the new end and add two port
  bolts, with no other part changed except the covers for the new barrel

#### Scenario: A compact gun
- **WHEN** a gun is built with no barrel
- **THEN** the ESP32-CAM nose plugs into the receiver's front port and
  the gun aims and fires

### Requirement: Bones carry nothing bought
The receiver, barrel, grip and rear cap SHALL carry only connections
(ports, tenons, rails, sockets and bolt holes). Every board, camera, cell,
switch, regulator, LED and lead SHALL be held by a module.

#### Scenario: A bare bone
- **WHEN** a bone is taken out of an assembled gun
- **THEN** no purchased part is attached to it

### Requirement: Rails take carrier plates
The receiver and the barrel SHALL each carry channels on both inner side
walls that take a 2 mm carrier plate, 34 mm tall, sliding in from either
open end. A carrier SHALL be held lengthwise by printed spacers and by
whatever is plugged into the next port.

#### Scenario: Moving a carrier
- **WHEN** the feedback carrier is moved from the receiver into the
  barrel's rails
- **THEN** it fits the same channels and is held by spacers and the next
  port's module, with no new part

### Requirement: A module sits inside one bone
No module SHALL span a joint between two bones, so that a module can go
in any bone that has its connection, and every bone comes apart from its
neighbour without removing a module from it.

#### Scenario: Taking the barrel off
- **WHEN** the barrel's two port bolts are removed
- **THEN** the barrel comes off with its own modules inside, and the
  receiver keeps its own

### Requirement: The trigger sits at the top of the grip's front
The trigger module SHALL sit in a pocket at the top of the grip's front,
held by one M3 bolt. Its blade SHALL hang from a pivot, be pulled back
toward the palm, and press the switch with the blade's tail above the
pivot. The reach from the back of the grip to the blade SHALL be
60–70 mm.

#### Scenario: Pulling with the index finger
- **WHEN** a user holds the grip and pulls the trigger with the index
  finger
- **THEN** the blade moves back toward the palm and the switch actuates

### Requirement: The Pi's cables plug in under the barrel
The barrel SHALL have a window in its floor below the Pi's ports, so that
the HDMI cable, a USB device or host cable and the Pi's power plug fit
straight into the Pi from below with every cover fitted. No external
cable SHALL run inside the gun. A bolted clamp at the window SHALL take
any pull on the cables.

#### Scenario: Plugging into a TV
- **WHEN** a user plugs a mini-HDMI cable into an assembled Pi gun
- **THEN** it goes straight into the Pi through the window, with no
  cover or module removed

#### Scenario: A tug on the cable
- **WHEN** the HDMI cable is pulled hard below the gun
- **THEN** the clamp holds, and the plug at the Pi stays seated

### Requirement: The Pi runs from any battery drawer
The Pi kit SHALL run from each battery drawer (4×AA, 4×AAA, 18650)
through the hub's switch and regulator, which feed the Pi's power port by
a right-angle plug that fits only one way round. On a USB host cable the
Pi SHALL take power and data through its USB port at the window, and the
hub SHALL then run from the Pi.

#### Scenario: A Pi on the 18650 drawer
- **WHEN** a Pi gun with the 18650 drawer is switched on
- **THEN** the Pi boots and runs from the cell, with no cable fitted

#### Scenario: A Pi on a host cable
- **WHEN** a Pi gun with the tether drawer fitted without its cable is
  plugged into a host at the window
- **THEN** the Pi runs as a USB gun, and the hub's LEDs and the trigger
  work from the Pi's 5 V

### Requirement: The hub gathers power and wiring
A hub module on the receiver's rails, directly above the grip, SHALL hold:
- the regulator;
- the power switch;
- the power and status LEDs;
- one polarized socket for each module's lead;
- a 5 V and a GND test pin.

The battery, trigger and feedback leads SHALL each be at most 60 mm long.

#### Scenario: Testing the supply
- **WHEN** a meter is put on the hub's test pins of a switched-on battery
  gun
- **THEN** it reads 4.75–5.25 V, with no cover removed but the left
  receiver cover

#### Scenario: Taking one module out of the circuit
- **WHEN** any one module's plug is pulled from the hub
- **THEN** every other module still works, and the pulled module can be
  tested on its own

### Requirement: The ESP32-CAM can be flashed and read in place
The ESP32-CAM nose SHALL carry a 6-pin socket and a BOOT button on its
underside, wired by a plug on the board's own header pins:
- GND, TX (U0T) and RX (U0R) on the socket, for a 3.3 V USB-serial
  adapter;
- the BOOT button between IO0 and GND;
- the board's VCC pin, which is an output, left unconnected.

#### Scenario: Reading the log
- **WHEN** a USB-serial adapter is plugged into the socket of a
  switched-on ESP32-CAM gun
- **THEN** the board's serial log reads at its normal baud rate, with no
  part removed

#### Scenario: Flashing in place
- **WHEN** the user holds BOOT while switching the gun on and then flashes
  through the socket
- **THEN** the board takes the new firmware and runs it after a power
  cycle

### Requirement: Optional Start and Select buttons
A Pi gun SHALL accept two optional buttons, Start and Select, on its left
side next to the power switch. Each SHALL be wired through the hub between a header
GPIO pin and GND, on pins that nothing else uses. The README SHALL name
the pins, so the gun's configuration can use them.

#### Scenario: Starting a game
- **WHEN** a Pi gun with the buttons, running in console mode with the
  pins configured, has its Start button pressed
- **THEN** the game sees Start, and the trigger and status LED still work
  on their own pins

### Requirement: Bolts keep clear of what works
No bolt SHALL cross a module's space, a lead's path or a camera's field of
view. No bolt, nut or other metal part SHALL lie within 10 mm of a board's
PCB antenna: the ESP32-CAM's or the Pi Zero 2 W's.

#### Scenario: Every bolt fitted
- **WHEN** a gun of any valid configuration is assembled with every bolt
- **THEN** no bolt touches a module, a lead or a camera's view, and
  nothing metal is within 10 mm of either antenna

## MODIFIED Requirements

### Requirement: The core is a set of modules with one joint type
The case's structure SHALL be bones (receiver, barrel, grip, rear cap) and
modules. Every end of the receiver and barrel SHALL be the same port: a
31 × 45 mm opening, 12 mm deep, keyed by a rib under its top wall and held
by two M3 bolts. A barrel's tenon, the rear cap's tenon and either camera
module SHALL fit any port.

#### Scenario: A remixed barrel fits an existing receiver
- **WHEN** a barrel of a different shape is built with the standard tenon
- **THEN** it seats in the receiver's port and is held by the port's two
  bolts, with no change to the receiver

#### Scenario: Nothing goes in upside down
- **WHEN** a tenon or camera module is offered to a port upside down
- **THEN** the key rib stops it before its bolt holes line up

### Requirement: The core alone is a working gun
Every functional part (board, camera, cells, regulator, switches, trigger,
LEDs, feedback device, wiring) SHALL be held by modules on the bones. A
gun assembled with no covers SHALL aim and fire as it does with covers,
with printed spacer collars taking the covers' place under the bolts.

#### Scenario: Bench test without covers
- **WHEN** a gun is assembled with its bones, modules and spacer collars
  and no covers
- **THEN** every functional part is held in place, and the gun aims and
  its trigger works

### Requirement: One core takes either board
The core SHALL accept an ESP32-CAM kit or a Raspberry Pi Zero 2 W kit. The
bones, hub, trigger module, power drawers, feedback carriers and covers
SHALL be shared by both. Switching SHALL replace only the kit's parts:
- the ESP32-CAM nose; or
- the Pi camera module, the Pi sled and their leads.

#### Scenario: Converting an ESP32-CAM gun to a Pi gun
- **WHEN** a builder converts an ESP32-CAM gun on the AA drawer to the Pi
  kit
- **THEN** they take the nose off the muzzle port, slide the Pi sled into
  the barrel, fit the Pi camera module in the muzzle port and plug both
  leads into the hub, and they reuse every other part, the AA drawer
  included

### Requirement: The ESP32-CAM kit
The ESP32-CAM kit SHALL be a nose module whose tenon fits a port, held by
the port's own two bolts. It SHALL hold an AI-Thinker ESP32-CAM 24 mm in
front of the port, camera forward along the barrel axis, with two 1×6
plugs on its header pins. It SHALL have a place for a 470–1000 µF
capacitor across 5 V and GND, and keep metal at least 10 mm from the PCB
antenna.

#### Scenario: Flashing without unsoldering
- **WHEN** the builder needs to reflash the ESP32-CAM away from the gun
- **THEN** they remove the nose's two port bolts, unplug the two plugs
  from the header, and reach every header pin with the board still in the
  nose

#### Scenario: Antenna clearance
- **WHEN** the ESP32-CAM kit is assembled in any valid configuration
- **THEN** no bolt, nut, cell or other metal part lies within 10 mm of
  the PCB antenna

#### Scenario: The gun's length
- **WHEN** an ESP32-CAM gun and a Pi gun are built with the same barrels
- **THEN** the ESP32-CAM gun is about 35 mm longer, because its board
  rides in front of the muzzle port

### Requirement: The Pi Zero 2 W kit
The Pi kit SHALL hold a Raspberry Pi Camera Module 2 or 3 on a camera
module in the muzzle port, and the Pi Zero 2 W on a sled in the barrel
right behind it, joined by a 38 mm Pi Zero camera ribbon. The Pi's ports
SHALL face the window in the barrel's floor. The micro-SD card SHALL be
removable after taking off only the barrel.

#### Scenario: Either camera module fits
- **WHEN** the Pi camera module is fitted with a Camera Module 2 or a
  Camera Module 3
- **THEN** the camera is held on the same mounting points and faces
  forward along the barrel axis

#### Scenario: Swapping the SD card
- **WHEN** the builder removes the barrel's two port bolts and pulls the
  barrel off
- **THEN** the micro-SD card can be pulled and reinserted at the sled's
  rear end, without removing the sled, the covers or any other module

### Requirement: The Pi has room to cool
The case SHALL provide vent openings in the barrel and its covers over the
Pi's processor and room for a heatsink up to 14×14×6 mm on it. With the
heatsink fitted, the processor's temperature in the closed case SHALL stay
within 10 °C of the same board running the same load in open air.

#### Scenario: Temperature after a long session
- **WHEN** the Pi gun runs the aim pipeline for 30 minutes in the closed
  case, and again as a bare board in open air at the same room temperature
- **THEN** the in-case processor temperature is at most 10 °C higher

### Requirement: Interchangeable power drawers
The grip SHALL take one of four power drawers through the same bay: 4×AA,
4×AAA, one 18650 cell, or a USB tether. Each drawer SHALL be keyed so it
can only be inserted the right way round, and SHALL be locked in by a
captive thumbscrew in its base.

#### Scenario: Changing battery type
- **WHEN** a builder replaces the AA drawer with the 18650 drawer
- **THEN** the new drawer slides into the same bay and its thumbscrew
  locks it, with no other part changed

#### Scenario: A reversed drawer does not go in
- **WHEN** a drawer is offered to the bay the wrong way round
- **THEN** it does not enter far enough to make electrical contact

### Requirement: Batteries swap without tools
A battery drawer SHALL come out and go back in by hand, with no tool, no
cover or other part removed and no wire unplugged. It SHALL make its
electrical connection when it is pushed home, and its thumbscrew SHALL
turn by hand.

#### Scenario: Swapping AA cells
- **WHEN** the AA cells run flat
- **THEN** the user undoes the thumbscrew by hand, pulls the drawer,
  changes the cells, pushes it home, tightens the thumbscrew, and the gun
  powers up

### Requirement: The board gets a steady 5 V from any battery drawer
Every battery drawer SHALL feed the hub's regulator, which SHALL supply
the board and the feedback device's 5 V with 4.75–5.25 V at up to 1.5 A
across the drawer's whole usable cell voltage range, alkaline or NiMH for
AA and AAA.

#### Scenario: Nearly flat NiMH cells
- **WHEN** four NiMH AA cells have discharged to 1.0 V each and the
  ESP32-CAM is streaming
- **THEN** the board still receives 4.75–5.25 V

#### Scenario: The Pi at full load
- **WHEN** four NiMH AA cells at 1.0 V each power a Pi gun that is aiming,
  with HDMI connected and the vibration motor running
- **THEN** the Pi's supply stays within 4.75–5.25 V

### Requirement: One switch turns a battery gun on and off
A battery-powered gun SHALL have one power switch on the hub, reachable on
the gun's left side above the grip, where a safety would be, and operable
with the covers fitted. It SHALL be in the path from the drawer to the
regulator and to the solenoid.

#### Scenario: Switching off
- **WHEN** the user moves the power switch to off
- **THEN** the regulator, the board and any feedback device draw no
  current from the cells

### Requirement: Valid configurations
A configuration SHALL name: board kit, power drawer, trigger mechanism,
switch plate, number of barrels (0, 1 or 2), feedback device or none,
whether the Start and Select buttons are fitted, and style.
- The ESP32-CAM kit SHALL accept any drawer and any number of barrels.
- The Pi kit SHALL accept any drawer, at least one barrel, and the
  buttons.
- The solenoid SHALL be refused on the USB tether.

#### Scenario: A Pi on batteries
- **WHEN** a configuration pairs the Pi kit with a battery drawer and one
  barrel
- **THEN** the build succeeds, and the gun has the hub's switch and
  regulator and the window under the barrel

#### Scenario: A Pi with no barrel is refused
- **WHEN** a configuration pairs the Pi kit with no barrel
- **THEN** the build refuses before generating any part, and names the
  board, the barrel count and the reason

#### Scenario: A solenoid on the tether is refused
- **WHEN** a configuration pairs the recoil solenoid with the USB tether
- **THEN** the build refuses before generating any part, and names the
  device, the drawer and the reason

#### Scenario: An ESP32-CAM on the tether
- **WHEN** a configuration pairs the ESP32-CAM kit with the USB tether
- **THEN** the build succeeds and the board is powered from the cable

### Requirement: The trigger's mechanism is swappable
The trigger SHALL be one of two mechanisms in the same grip pocket, held
by the same one bolt: a lever turning on an M3 bolt, or a push button
pressed straight back. Changing mechanism SHALL replace only that
mechanism's printed parts and pivot. The switch plates, the switch and
the lead to the hub SHALL be the same for both.

#### Scenario: A button instead of a lever
- **WHEN** a builder replaces the lever module with the button module,
  keeping the MX plate
- **THEN** the switch plate, switch and lead are reused, the module is
  held by the same one bolt, and pressing the button actuates the switch

### Requirement: The trigger and LED use the existing pins
The trigger SHALL be wired through the hub between the board's trigger
input and GND, on the pins the existing software defaults to: GPIO13 on
the ESP32-CAM, and GPIO17 (header pin 11) on the Pi. The hub's status LED
SHALL be driven by the Pi's GPIO27 (header pin 13).

#### Scenario: No software change
- **WHEN** a case is built with either kit and the board runs its
  existing default configuration
- **THEN** the trigger and the status LED work without editing any
  setting

### Requirement: The status LED is visible in use
The board's status SHALL be visible from the shooter's position with the
covers fitted. On a Pi gun, the hub's status LED SHALL show through the
left cover. On an ESP32-CAM gun, a light guide in the nose SHALL carry
the board's own LED to a window on the nose's top. The hub's power LED
SHALL show next to the switch in both kits.

#### Scenario: Checking the solve state while aiming
- **WHEN** the user holds the assembled gun aimed at the screen
- **THEN** they can see the status LED's pattern without turning the gun

### Requirement: Every connection between modules is a plug
Every electrical connection that crosses a module boundary SHALL be a
polarized plug and socket, and every module SHALL connect to the hub by
one lead. The ESP32-CAM's leads SHALL plug onto its own header pins. No
soldered joint SHALL cross a module boundary. The case SHALL need no
custom-made circuit board, only off-the-shelf modules, perfboard and
wires.

#### Scenario: Removing the trigger module
- **WHEN** the trigger module is taken out
- **THEN** its lead unplugs at the hub, and no wire needs cutting or
  desoldering

### Requirement: The gun comes apart with one hex key
Taking the gun fully apart into bones, modules and unplugged electronics
SHALL need only a 2.5 mm hex key and at most 12 bolts. All SHALL be M3
socket-head in two lengths: the through-bolts and the trigger's bolt.
The drawer's thumbscrew turns by hand, and every nut sits in a hex pocket,
so no wrench is needed. No glue, cutting or desoldering SHALL be needed,
and reassembly SHALL be the same steps reversed.

#### Scenario: A full teardown and rebuild
- **WHEN** a builder takes an assembled long gun apart and rebuilds it
- **THEN** they used only the hex key, removed at most 12 bolts, and the
  rebuilt gun works as before

### Requirement: Screws never thread into plastic
Every bolt SHALL engage a metal nut, never a thread formed in a printed
part. Every through-bolt SHALL take a nylon-insert lock nut, so repeated
assembly does not wear the joints and vibration does not loosen them.

#### Scenario: Twenty rebuilds
- **WHEN** the gun has been taken apart and rebuilt 20 times
- **THEN** every joint still tightens fully and none has worked loose

#### Scenario: An hour of feedback
- **WHEN** a gun with the solenoid fires once a second for an hour
- **THEN** no nut has turned

## REMOVED Requirements

### Requirement: The Pi's USB cable is anchored at the grip base
**Reason**: The Pi now sits in the barrel. Its cables plug into it at the
window in the barrel's floor and never run through the grip.
**Migration**: See "The Pi's cables plug in under the barrel" and "The Pi
runs from any battery drawer". The USB tether drawer stays for the
ESP32-CAM; a Pi on a host cable uses the tether drawer fitted without its
cable.
