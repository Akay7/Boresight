# The Boresight gun case

A printable, modular case for the two self-contained guns: the ESP32-CAM
(Wi-Fi to the server) and the Raspberry Pi Zero 2 W (a USB mouse on its
own). One core takes either board, any of four power drawers and either
trigger switch. Two skin styles change how it looks, and a published
interface lets you design your own.

**Never yet printed.** Every part is checked by a computer for bed fit,
support-free printing, interference with its neighbours and with every
purchased part, the camera's view, and the skin keep-outs (`uv run pytest`
here). Nothing has been printed or assembled. Every dimension of a
purchased part is from a datasheet or a typical listing until measured
(see `src/boresight_case/vendor.py`, which says which), and the checklist
at the end lists what only a printed gun can confirm.

    cd hardware/case
    uv sync
    uv run boresight-case build my-gun.toml --out dist    # one configuration
    uv run boresight-case build --all --out dist          # every shipped one
    uv run boresight-case coupon --out dist               # the fit coupon first
    uv run pytest -q                                      # the checks

## Modules

The core is a set of modules. Barrel, grip and rear cap each join the
receiver through the same joint: a rectangular tenon in a socket, held by
one M3 x 12 screw from the gun's right side into a nut in the tenon. A
remixed barrel or grip fits as long as it carries that tenon.

| Module | Part | What it holds |
| --- | --- | --- |
| Receiver | `receiver` | The hub. Sockets for the barrel (front), rear cap (back) and grip (underneath); rails under its floor for the trigger cassette; rails inside for the Pi's sled |
| Barrel | `barrel` | The camera bulkhead in its muzzle, keyed by a rib under its top wall |
| Grip | `grip` | The power drawer's bay, keyed by a rib down its front wall, and the two spring contacts under the bay's ceiling |
| Rear cap | `rear-cap` | The power switch, the regulator and the Pi kit's status LED. Its tenon is hollow: the Pi's micro-SD card comes out through it |
| Trigger | `trigger-cassette-*`, `trigger-lever-*`, `button-*`, `switch-plate-*` | The trigger in one of three mechanisms (a lever on a filament pin or an M3 bolt, or a push button), its switch on a swappable plate, its return spring and stop |
| Camera bulkhead | `bulkhead-esp32-cam` or `bulkhead-pi-camera` | The camera, behind the muzzle's aperture |
| Board sled | `sled-pi-zero-2w` | The Pi, in the receiver (Pi kit only) |
| Power drawer | `drawer-aa`, `drawer-aaa`, `drawer-18650`, `drawer-usb` | Cells, the 18650 charger, or the USB tether's cable |

The core alone is a working gun. Skins only cover it.

### Fasteners

Every screw is M3 socket-head, M3 x 12 for joints and M3 x 8 for skins,
and goes into a captive nut, never a thread in plastic, so the gun comes
apart and back together without wearing. A full teardown needs only a
2.5 mm hex key. The nut pockets are a press fit: push each nut in with a
screw from the other side before assembly.

`fastener = "insert"` in `[printer]` puts a hole for a 4.6 mm M3 heat-set
insert where each nut was. It needs a soldering iron once, and nothing
after.

## The trigger

The trigger is a cassette that hangs under the receiver's floor between
two rails, held by one screw from below. It comes in three mechanisms,
all on that same mount and all taking the same two switch plates. Pick
one with `mechanism` in `[build]`:

| `mechanism` | Parts | How it moves |
| --- | --- | --- |
| `filament` (default) | `trigger-cassette-filament`, `trigger-lever-filament` | A lever on a 22 mm piece of 1.75 mm filament, the pivot pin. Nothing to buy |
| `bolt` | `trigger-cassette-bolt`, `trigger-lever-bolt` | The same lever on an M3 x 12, the pivot bolt: a steel axle that does not wear |
| `button` | `button-cassette`, `button-plunger`, `button-cap` | No lever: a push button, pressed straight back, that moves exactly as far as the switch |

Every mechanism meets the trigger switch at the same place, so the switch
plates (`switch-plate-mx`, `switch-plate-microswitch`), the switch, its
return spring (a ballpoint pen's usually fits, seated on a spigot on the
plate) and the lead to the board are the same whichever you fit.

### Building the cassette

1. Snap the trigger switch into its plate and solder its two leads to a
   JST-XH 2-way plug (the trigger plug).
2. Drop the plate into the slot in the cassette's top plate until it rests
   on the grooves' ends. The trigger plug sits in its pocket beside it.
3. Fit the return spring on its spigot, then the moving part:
   - `filament`: hold the lever against the spring and push the pivot pin
     through both side walls and the lever's hub.
   - `bolt`: press the pivot bolt's nut into the pocket in the right-hand
     boss, hold the lever in place, and drive the pivot bolt in from the
     left: its head sinks into the left boss.
   - `button`: push the plunger, head first from below and behind, rod
     forward through the guide block, and press the cap onto the rod's
     end.
4. Fit the stop's lock nut (nylon insert): for a lever, into the slot
   under the front wall, then turn the stop screw into it from the front;
   for the button, slide it into the slot in the right wall, then turn the
   stop screw into it from the front, its head standing proud of the
   block.
5. Set the cassette between the rails under the receiver, its trigger plug
   up through the floor, and fit the cassette screw from below into the nut
   on the receiver's floor.

**Changing the switch.** Undo the cassette screw, lift the cassette out,
take out the moving part and spring, and lift the plate out. Fit the other
plate and reverse. Nothing else changes.

**Changing the mechanism.** Undo the cassette screw and swap the whole
cassette; move the switch plate, switch and spring across. The trigger
plug and the lead to the board stay as they are.

**Setting the stop.** The stop screw decides where the pull ends: past
the switch's actuation, before its end of travel. As built, an MX switch
stops at 3.0 mm of its 4.0 mm (actuates at 2.0); a lever microswitch at
2.0 mm (operates at 1.6, bottoms at 2.4). On a lever, the screw's tip
meets the lever's upper arm: with the trigger pulled fully, turn it in
until the switch clicks with a little travel to spare. On the button, the
cap's back meets the screw's head: reach it with the hex key through the
hole in the cap, and turn it out to shorten the press or in to lengthen
it. Either way the lock nut's nylon ring holds the screw wherever you
leave it, so the hex key is the only tool.

## The board kits

### ESP32-CAM

The whole board stands on the camera bulkhead, camera forward. The
camera module sits in a pocket that sets the aim; the board slides down
into grooves behind it and rests on the bulkhead's floor. The barrel's top
wall keeps it there. The front plate covers the white flash LED, so it can
never shine out of the muzzle or into the lens.

| Connection | Pin | Notes |
| --- | --- | --- |
| Trigger plug | GPIO13 and GND | Dupont housings on the header pins, from the cassette's JST plug |
| Power | 5V and GND | From the regulator in the rear cap; the 470-1000 uF capacitor sits in a cradle on the bulkhead's tail, across 5V and GND |
| Status LED | GPIO33 (on the board) | A 45 mm piece of clear 1.75 mm filament, the light guide, carries its glow up through a window in the barrel's top |

These are the firmware's defaults (`firmware/boresight-cam`): no setting
needs changing.

**Reflashing.** Pull the light guide up out of the barrel's window, undo
the bulkhead screw under the barrel, and slide the bulkhead forward out of
the muzzle. Every header pin is reachable with the board still on the
bulkhead: unplug the leads, connect the USB-serial adapter, and hold GPIO0
to GND as it powers up.

Nothing metal comes within 10 mm of the board's PCB antenna (checked for
every drawer), and the u.FL route for an external antenna stays open.

### Raspberry Pi Zero 2 W

A Camera Module 2 or 3 sits on four pegs on the camera bulkhead, held by a
clip over its top edge; both use the same bulkhead. The Pi stands on a
sled in the receiver, camera connector forward and ports down. Four pegs
go through its holes and two clips hold its edges. A 150 mm Pi Zero camera
cable joins them down the barrel. A 14 x 14 mm heatsink on the processor
faces vent slots in the receiver's right wall and top.

| Connection | Header pin | Notes |
| --- | --- | --- |
| Trigger plug | GPIO17 (pin 11) and GND (pin 9) | One 3-way Dupont housing on pins 9, 11, 13 |
| Status LED | GPIO27 (pin 13) and GND (pin 9) | The 5 mm LED and its 330 ohm resistor, in the rear cap |
| USB | The data port | A 90-degree micro-USB plug; the cable runs back over the grip socket, down the grip and through the tether drawer |

These are the defaults in `deploy/pi/boresight-gun.example.toml`.

**The micro-SD card.** Undo the rear cap's screw and slide the cap back:
the card comes straight out of the back of the receiver.

## Power

The ESP32-CAM runs from a battery drawer or the USB tether:

    cells in the drawer -> drawer's flat contacts -> spring contacts in
    the grip -> power switch (rear cap) -> regulator (rear cap) -> 5 V to
    the board

One buck-boost regulator in the rear cap makes 5 V from anything between
about 3 and 6.5 V, so every drawer feeds the same path. The rocker switch
is in the rear cap's back face, under your thumb, and works with the skins
on. Every connection between modules is a plug.

The Pi takes its power and its data through its one USB cable to the host,
so a Pi gun always uses the tether drawer, and the build refuses a Pi with
a battery drawer.

| Drawer | For | Holds |
| --- | --- | --- |
| `aa` | ESP32-CAM | A 2 x 2 AA holder (alkaline or NiMH) |
| `aaa` | ESP32-CAM | A 2 x 2 AAA holder |
| `18650` | ESP32-CAM | A 1 x 18650 holder and a USB-C TP4056 charger with protection |
| `usb` | ESP32-CAM or Pi | The cable, weaving between three posts that take any pull off the plug |

**Changing cells.** Press the latch tongue at the front of the grip's base
back, from below, and pull the drawer out. Change the cells, push it back
until it clicks. Its contacts meet the springs as it latches: no tool, no
wire to unplug. It only goes in one way round.

**Charging the 18650.** Turn the switch off and plug a USB-C charger into
the port in the grip's base. The charger's LEDs show through a window in
the grip's front.

**Cell safety.** Use a protected 18650 (a button-top cell up to 70 mm), or
rely on the charger's DW01 protection, which disconnects the cell on
over-discharge, over-current and short circuit. Mind the polarity marks
in the holders. NiMH cells in series should not be run flat: switch off
when the ESP32-CAM starts resetting.

## Skins

The look is a separate set of parts over the core: for each of barrel,
receiver and grip, a left and a right half. Each half hooks into a slot in
the core at one end and takes one M3 x 8 screw at the other. Changing
style means changing skins only; nothing inside moves, so the gun keeps
its zero. Accent parts print separately, in a second colour, and press in
on pegs.

| Style | Parameter | Default | Range | What it does |
| --- | --- | --- | --- | --- |
| `minimal` | `shroud_length` | 0 | 0 to 20 | How far the barrel's skins reach past the muzzle (mm) |
| `minimal` | `chamfer` | 1.2 | 0.4 to 2 | The 45-degree chamfer on every outer edge (mm) |
| `minimal` | `grip_texture` | `grooves` | `grooves`, `none` | Shallow grooves across the grip's flanks |
| `blaster` | `shroud_length` | 16 | 6 to 30 | The flared muzzle shroud's length (mm) |
| `blaster` | `fin_height` | 7 | 0 to 12 | The dorsal fin's height over the barrel (mm); 0 removes it |
| `blaster` | `chamfer` | 2 | 1 to 2.2 | The faceting chamfer (mm) |
| `blaster` | `accents` | true | true, false | Side stripes and a muzzle ring, as separate parts |

Set them in `[style]`. A value outside its range is refused, naming the
parameter and the range. Every value inside it builds skins that pass
every check.

### Designing your own skin

Every build writes the skin interface to `interface/`:
`skin-interface.step` (open it in FreeCAD, Fusion, Onshape or any CAD
tool) and `skin-interface.json` (the same, as numbers). Coordinates are the
gun's, in mm: x forward along the camera axis, y to the gun's left, z up.

- **Core envelope.** The solid named `core envelope` is the core's outside.
  A skin may touch its surface, never enter it, except through the hook
  slots.
- **Attachment points.** Six, one per skin half: `barrel-left`,
  `barrel-right`, `receiver-left`, `receiver-right`, `grip-left`,
  `grip-right`. Each has a screw (`attachment: <name> screw`): a 3.4 mm
  hole through the skin on that axis, with a 6.2 mm counterbore leaving
  1.2 mm under the head, for an M3 x 8. And it has a hook
  (`attachment: <name> hook`): a 4 mm stem through the core's slot, ending
  in a 1.6 mm 45-degree wedge that catches behind the wall. Lay the skin on
  with the wedge through the slot, slide it home along the slot, then
  screw it down. The JSON gives each position, axis, wall normal and slide
  direction.
- **Keep-out zones.** No skin may enter any of these named solids:
  `view ov2640`, `view cm2`, `view cm3` (each camera's field of view out of
  the muzzle); `vents` (the Pi's cooling slots); `trigger` (the trigger's
  travel, the finger's room and the stop and cassette screws' access);
  `drawer and latch` (everything under the grip's base); `charge indicator`
  (the 18650 charger's LEDs); `power switch`; `status LEDs` (the barrel's
  light guide window and the rear cap's LED); `screw access` (joint and
  bulkhead screw heads); and `rear cap and bulkhead removal` (their way
  out).
- **Print rules.** Skins print flank down: give each half a flat outer
  flank, no downward face steeper than 45 degrees from vertical, and no
  bridge longer than 10 mm. The shipped skins are 3.2 mm thick at the
  flank.

Then check your parts, exported as STL or 3MF in the interface's
coordinates:

    uv run boresight-case check-skin my-gun.toml left.stl right.stl

It reports each part as conforming, or every violation with the zone or
attachment point it breaks.

## Printing

Print the fit coupon first (`boresight-case coupon`, under 10 g and a few
minutes). Push its tenon into each socket. The dots by the one it slides
into without play give the clearance (1 dot 0.15 mm to 5 dots 0.35 mm):
set `clearance` in `[printer]`. The nut pocket that grips a nut without
forcing it gives `interference` (1 dot 0, 2 dots 0.05, 3 dots 0.10). Try
the round pegs in a Pi's mounting hole the same way. Then build and print
the gun.

Parts are exported already lying in their print orientation: drop them in
the slicer and do not rotate them. Every part fits a 180 x 180 x 180 mm
bed (set another in `[printer] volume`, and the build refuses any part
that does not fit). Every part prints without support: turn supports off.

| Parts | Material | Settings |
| --- | --- | --- |
| Trigger lever, switch plates, cassette, drawers (their latch flexes) | PETG | 4 perimeters (3 for drawers), 40-60% infill |
| Receiver, barrel, grip, rear cap | PLA or PETG (PETG if it may get warm) | 4 perimeters, 25-30% infill |
| Bulkheads, sled | PLA or PETG | 3 perimeters, 30% infill |
| Skins and accents | PLA or PETG | 3 perimeters, 15-20% infill |

The bill of materials (`bom.md`) gives each part's settings. Use a 0.4 mm
nozzle and 0.2 mm layers.

**Without Python.** CI builds every shipped configuration on each push
and keeps them as one downloadable artifact, `case`: open the
repository's Actions tab, pick a run of the CI workflow and download it.
It is a parts library: `parts/` holds every distinct part's STL and 3MF
once, `step/` their STEP files, `interface/` the skin interface, and
`configurations/<name>/` each configuration's bill of materials (which
names the files in `parts/` to print) and exploded view. Configurations
are named board, drawer, mechanism and switch, and style, like
`esp32-cam_aa_filament-mx_minimal` or `pi-cm3_usb_button-microswitch_blaster`.

With Python and uv:

    uv run boresight-case build my-gun.toml --out dist
    uv run boresight-case build --all --out dist
    uv run boresight-case coupon --out dist

## What only a printed gun can confirm

Everything above is checked by computer; none of it has been printed.
Tick these off on a first build, and revise `vendor.py` (with caliper
measurements and their source) and the defaults wherever the gun
disagrees. Each item names the scenario of the specification it confirms.

**Printing**

- [ ] The coupon prints in under 30 minutes, and its best clearance on the
  reference printer is recorded here: ____ mm (*Tuning before the full print*)
- [ ] Every part slices with supports off and no unsupported overhang the
  slicer flags (*Slicing with supports off*)
- [ ] Every exported part loads in the slicer flat on the bed, the way it
  was designed to print (*Loading a part*)
- [ ] Buying exactly the bill of materials for an AA ESP32-CAM gun leaves
  nothing missing and no screw over (*Shopping for an AA ESP32-CAM gun*)
- [ ] A CI run's artifact for a configuration holds everything to print it
  (*Printing without Python*)

**Assembly and teardown**

- [ ] With no skins fitted, every part is held and the gun aims and fires
  (*Bench test without skins*)
- [ ] A full teardown and rebuild with only the 2.5 mm hex key, removing at
  most 12 screws (*A full teardown and rebuild*)
- [ ] Twenty rebuilds, and every joint still tightens fully (*Twenty rebuilds*)
- [ ] The trigger cassette comes out by its screw and its plug, nothing
  cut or desoldered (*Removing the trigger cassette*)
- [ ] An ESP32-CAM gun converts to the Pi kit with only the bulkhead, sled
  and drawer changed (*Converting an ESP32-CAM gun to a Pi gun*)

**Board kits**

- [ ] The ESP32-CAM reflashes with the bulkhead out, every header pin
  reachable (*Flashing without unsoldering*)
- [ ] Both Camera Modules sit on the same pegs, facing forward (*Either
  camera module fits*)
- [ ] The micro-SD card comes out with only the rear cap off (*Swapping the
  SD card*)
- [ ] A hard tug on the Pi's cable at the grip base leaves its plug seated
  (*A tug on the cable*)
- [ ] After 30 minutes of aiming, the Pi's processor is within 10 C of the
  same board in open air: in case ____ C, open air ____ C (*Temperature after
  a long session*)
- [ ] A frame captured through the muzzle shows no part of the case in any
  corner, for each camera (*No vignetting*)
- [ ] The trigger and status LED work on the default settings, on both
  kits (*No software change*)
- [ ] The status LED is visible while aiming, through the light guide and in
  the rear cap (*Checking the solve state while aiming*)
- [ ] The ESP32-CAM's Wi-Fi range inside the case is enough at the
  distance you play from: ____ m

**Power**

- [ ] Each drawer slides in, latches and powers the gun; the 18650 drawer
  replaces the AA drawer with nothing else changed (*Changing battery type*)
- [ ] A drawer offered the wrong way round does not enter far enough to
  touch the contacts (*A reversed drawer does not go in*)
- [ ] AA cells change without tools or unplugging anything (*Swapping AA
  cells*)
- [ ] The regulator gives 4.75 to 5.25 V at 1 A from 3.0 V in, and from four
  NiMH cells at 1.0 V each while streaming (*Nearly flat NiMH cells*)
- [ ] With the switch off, the gun draws nothing from the cells
  (*Switching off*)
- [ ] The 18650 charges through the grip's base with the switch off, its LED
  visible (*Charging overnight*)
- [ ] Run down, the 18650 is cut off by its protection (*Running the cell
  down*)

**Trigger**

- [ ] An MX-style switch snaps into its plate and the trigger actuates it
  (*Fitting an MX-style switch*)
- [ ] The microswitch plate swaps in with the lever, cassette and lead
  unchanged (*Changing to a microswitch*)
- [ ] A hard pull or press ends on the stop screw, past actuation, with
  either plate and every mechanism (*A hard pull*)
- [ ] The trigger returns and releases on every pull, with either plate
  and every mechanism (*Release with a light microswitch*)
- [ ] The bolt cassette and lever replace the filament-pin pair with the
  plate, switch and lead reused (*Changing from the filament pin to a
  bolt*)
- [ ] The button, with the MX plate, actuates the switch and moves as far
  as it does (*A button instead of a lever*)

**Skins**

- [ ] Changing style on an assembled gun touches only skins and their
  screws (*Changing style on an assembled gun*)
- [ ] Each skin's screw holes line up with the core's nuts (*A skin's
  screws line up*)
- [ ] The drawer comes out with the skins on (*Battery swap with skins on*)
- [ ] Accent parts printed in a second colour press in without glue (*A
  two-colour gun*)
- [ ] After a skin swap the aim point is unchanged, no re-zeroing needed
  (*Restyling keeps the zero*)
