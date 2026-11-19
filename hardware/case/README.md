# The Boresight gun case

A printable, modular case for the two self-contained guns: the ESP32-CAM
(Wi-Fi to the server) and the Raspberry Pi Zero 2 W (a USB mouse, or a
console on a TV, on its own). One set of bones takes either board, one,
two or no barrels, any of four power drawers, either trigger mechanism and
switch, a feedback device, and Start and Select buttons. Two cover styles
change how it looks, and a published interface lets you design your own.

**Never yet printed.** Every part is checked by a computer for bed fit,
support-free printing, interference with its neighbours and with every
purchased part, the bolts' clearance from everything that works, the
antennas, the camera's view and the cover keep-outs (`uv run pytest`
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

The case is three layers. **Bones** carry only connections. **Modules**
are everything that works, each in one bone. **Covers** give the look and
hold nothing up.

Every end of the receiver and of a barrel is the same **port**: a 31 x 45
mm opening, 12 mm deep, keyed by a rib under its top wall. Whatever fills
it carries the standard tenon: a barrel, the rear cap, the Pi's camera
module or the ESP32-CAM's nose. A remixed barrel fits as long as it carries
that tenon. Inside the receiver and the barrels, **rails** on both walls
take 2 mm carrier plates, between the port zones at each end.

| Module | Part | What it is |
| --- | --- | --- |
| Receiver | `receiver` | A bone. Ports at both ends, rails on both walls, the grip's socket underneath, and in its left wall the switch's slot, the LEDs' windows and the buttons' holes |
| Barrel | `barrel` | A bone, the same part for each barrel. Its tenon goes in the port behind it; its muzzle is a port. Rails, the window in its floor and the vent in its right wall |
| Grip | `grip` | A bone. The drawer's bay, the trigger's pocket at the top of its front, a boss down its back for the backstrap bolt and one at the bottom of its front for the drawer's thumbscrew |
| Rear cap | `rear-cap` | A bone: a plate and the tenon |
| Hub | `hub` | On the receiver's left rails above the grip: the regulator, the ideal diode, the power switch, the power and status LEDs, a socket for every lead and the 5 V and GND test pins |
| Trigger | `trigger-housing-*`, `trigger-blade`, `button-plunger`, `switch-plate-*` | In the grip's pocket, held by one bolt. A blade on an M3 pivot bolt, or a push button; either switch on a swappable plate |
| Power drawer | `drawer-aa`, `drawer-aaa`, `drawer-18650`, `drawer-usb` | Cells, the 18650's charger, or the USB tether's cable, locked by a thumbscrew |
| Feedback | `feedback-vibration`, `feedback-solenoid`, `solenoid-strap`, `feedback-lra` | One optional carrier on the receiver's right rails |
| Buttons | `button-panel` | Start and Select, on the left rails ahead of the hub (Pi only) |
| Spacers | `spacer-*` | Fill the rest of each run, so every carrier is held lengthwise |
| ESP32-CAM kit | `nose-esp32-cam`, `nose-sleeve` | The nose, in the muzzle port, holding the board 24 mm ahead of it |
| Pi kit | `camera-pi`, `sled-pi-zero-2w`, `pi-retainer`, `cable-clamp` | The camera module in the muzzle port, the Pi on its sled in the last barrel, the posts that hold it there, and the cables' clamp |
| Covers | `skin-*`, `accent-*` | Halves for the receiver, each barrel and the grip, and a ring at the muzzle |
| Spacer collars | `spacer-collar` | Stand in for the covers' flanges on a bench build |

No module spans a joint, so each bone comes off with its own modules
inside, and the gun aims and fires with no covers at all.

### Steel only

Every joint, module and cover is held by steel through the plastic. No
printed hook, slide rail, snap or flexing latch holds a part, so a printed
feature never carries the load that keeps a part on the gun.

- **Port bolts.** Each port takes two M3 x 50 bolts across the gun, 6 mm in
  from its mouth, at z = +12 and -12. Each passes the left cover, both bone
  walls, the crush tube of whatever fills the port and the right cover, and
  takes a nylon-insert lock nut in a hex pocket in the right cover, on a
  washer under its head. The crush tube takes the clamp, so the bolt
  squeezes a solid stack, not a hollow box. Tighten each hand-tight plus a
  quarter turn.
- **The grip** is held by the grip bolt across its tenon, and its covers by
  the backstrap bolt through the boss down its back. Neither crosses the
  drawer's bay.
- **The trigger** is held by one M3 x 12 up through its housing's top plate
  into a nut on the receiver floor's inside.
- **The drawer** is locked by a captive M3 thumbscrew through its foot,
  into a nut in the grip's front boss. It turns by hand.

A standard gun has 9 bolts: two at each of three ports, the grip bolt, the
backstrap bolt, and the trigger's. A long gun has 11, a compact gun 7.
A full teardown needs only the 2.5 mm hex key. Every nut sits in a hex
pocket, so no wrench is needed, and no bolt threads into plastic. Inside a
module, boards are held by M2.5 screws into nuts in printed bosses; a
teardown leaves them alone.

**Building without covers.** Fit a `spacer-collar` on each side of each
through-bolt where a cover's flange would be: the same bolts then hold the
bones.

`fastener = "insert"` in `[printer]` puts a hole for a 4.6 mm M3 heat-set
insert where the trigger bolt's nut was. The through-bolts always take lock
nuts.

## The trigger

The trigger module sits in a pocket at the top of the grip's front, its
top plate against the receiver's underside, and is held by the trigger
bolt. It comes in two mechanisms in the same housing outline, both taking
the same two switch plates. Pick one with `mechanism` in `[build]`:

| `mechanism` | Parts | How it moves |
| --- | --- | --- |
| `bolt` (default) | `trigger-housing-bolt`, `trigger-blade` | A blade on an M3 x 12, the pivot bolt. Pulled back toward the palm, its tail, above the pivot, swings forward onto the switch |
| `button` | `trigger-housing-button`, `button-plunger` | No lever: a push button pressed straight back, its head on the switch, moving exactly as far as the switch does |

From the grip's back to the blade's face is about 68 mm at the finger.

### Building the trigger

1. Snap the trigger switch into its plate and solder the trigger lead to it.
2. Drop the plate into the slot in the housing's top plate until it rests
   on the grooves' ends: facing back for the blade, turned round for the
   button.
3. Fit the moving part and the return spring (a ballpoint pen's usually
   fits) on the spigot on the wall behind it:
   - `bolt`: press the pivot bolt's nut into the right-hand boss, hold the
     blade in place, and drive the pivot bolt in from the left.
   - `button`: set the plunger in, its tongue along the top, and fit the
     guide bolt and its nut under the tongue.
4. Fit the stop screw: drop its lock nut (nylon insert) into its slot, then
   turn the stop screw into it. For the blade it comes up from below the
   front block; for the button it goes through the wall behind the plunger,
   its head standing proud.
5. Feed the trigger lead up through the top plate, set the housing into the
   grip's pocket, and fit the trigger bolt from below, behind the blade,
   into the nut on the receiver floor's inside. The lead's plug goes into
   the hub's trigger socket from below.

**Changing the switch.** Undo the trigger bolt, lower the housing, take out
the moving part and spring, and lift the plate out. Fit the other plate and
reverse.

**Changing the mechanism.** Undo the trigger bolt and swap the whole
housing; move the switch plate, switch and spring across. The trigger lead
stays as it is.

**Setting the stop.** The stop screw decides where the pull ends: past the
switch's actuation, before its end of travel. As built, an MX switch stops
at 3.0 mm of its 4.0 mm (actuates at 2.0); a lever microswitch at 2.0 mm
(operates at 1.6, bottoms at 2.4). On the blade, an arm from it reaches
forward under the switch, and its tip drops onto the stop screw's tip:
with the trigger pulled fully, turn the screw up until the switch clicks
with a little travel to spare. On the button, the plunger's pad meets the
stop screw's head: reach it with the hex key through the hole in the pad.
The lock nut's nylon ring holds the screw wherever you leave it.

## The board kits

### ESP32-CAM

The board rides in the nose, 24 mm ahead of the muzzle port, camera
forward and **antenna down**. As the datasheet shows it, the camera folds
over the micro-SD slot at the board's 5V/3V3 end, which is up, about 10 mm
above the bore; the ESP32-S module and its PCB antenna are on the board's
back, at the other end. The nose's tenon fills the
muzzle port; a retainer sleeve inside the tenon, crossed by the port's two
bolts, presses the board against stops in front. Nothing metal comes within
10 mm of its antenna: the nearest bolt is about 30 mm away.

| Connection | Pin | Notes |
| --- | --- | --- |
| Trigger | GPIO13 and GND | Through the hub; the board's plug is a Dupont 1x6 on header row +1, pins 1-6 |
| Power | 5V and GND | From the hub's regulator, on the same plug; the 470-1000 uF capacitor sits under the debug board, across 5V and GND |
| Feedback | GPIO12, or GPIO14 (SDA) and GPIO15 (SCL) | On the same plug |
| Status LED | GPIO33 (on the board) | A 12 mm piece of clear 1.75 mm filament, the light guide, carries its glow up through a window in the nose's top |

These are the firmware's defaults (`firmware/boresight-cam`): no setting
needs changing.

**Flashing and reading the log in place.** A second plug on header row -1,
pins 3-8 (IO0, GND, VCC, U0R, U0T, GND), goes to the debug board under the
nose's top. Its 6-pin socket opens on the nose's top in the common FTDI
order: GND, nc, nc, RX (U0R), TX (U0T), nc. A 3.3 V USB-serial adapter
plugs straight in. VCC is left unconnected: it is an output, and the gun
powers the board. To flash, hold the BOOT button (IO0 to GND), beside the
socket, while switching the gun on, then flash through the socket. To read
the log, just plug in.

### Raspberry Pi Zero 2 W

A Camera Module 2 or 3 sits on four standoffs on the camera module in the
muzzle port; both use the same module. The Pi rides on its sled on the last
barrel's left rails, right behind it, ports facing down onto the window in
the barrel's floor, joined to the camera by a 38 mm Pi Zero camera ribbon.
The sled's front lug holds the camera board on its standoffs, and the
retainer's four posts, from the right rails, hold the Pi on its pegs. A
14 x 14 x 6 mm heatsink on the processor faces the vent in the barrel's
right wall.

| Connection | Header pin | Notes |
| --- | --- | --- |
| Trigger | GPIO17 (pin 11) and GND (pin 9) | Through the hub, on the Pi signal lead: one Dupont 1x10 on the odd pins 1-19 |
| Status LED | GPIO27 (pin 13) | The hub's status LED, beside the power switch, through the left cover |
| Start and Select | GPIO4 (pin 7) and GPIO10 (pin 19) | The optional buttons. Set `[pins] start = 4` and `select = 10` |
| Feedback | GPIO22 (pin 15), or I2C1 (pins 3 and 5) | The vibration motor or solenoid's drive, or the LRA's driver |
| Power | The PWR port | A right-angle micro-USB plug, on its lead from the hub |

These are the defaults in `deploy/pi/boresight-gun.example.toml`.

**Cables at the window.** HDMI (a right-angle mini-HDMI plug) and USB go
straight up into the Pi through the window, with every cover fitted; no
cable runs through the gun. A clamp bar under the barrel, on a hand-turned
thumbscrew, takes any pull on them. On batteries, the Pi runs from the hub
like any board. On a USB host cable, fit the tether drawer without its
cable and plug the host into the Pi's USB port at the window: the hub then
runs from the Pi, through its ideal diode.

**The micro-SD card.** Take the barrel off: the card comes out of the
sled's rear end.

## Power

Every drawer feeds the hub:

    cells in the drawer -> its flat contacts -> the battery lead's spring
    contacts in the grip -> the hub's power switch -> the regulator ->
    the ideal diode -> 5 V to the board and the feedback device

One 1.5 A buck-boost regulator on the hub makes 5.1 V from anything
between about 2.7 and 6.5 V, so every drawer feeds the same path, for
either board. The solenoid alone takes its pulses from the cells after the
switch, through a fuse, not through the regulator. The power switch comes
out of the receiver's left side above the grip, where a safety would be,
with the power LED beside it.

| Drawer | For | Holds |
| --- | --- | --- |
| `aa` | ESP32-CAM or Pi | A 2 x 2 AA holder (alkaline or NiMH) |
| `aaa` | ESP32-CAM or Pi | A 2 x 2 AAA holder |
| `18650` | ESP32-CAM or Pi | A 1 x 18650 holder and a USB-C TP4056 charger with protection |
| `usb` | ESP32-CAM or Pi | The tether's cable, weaving between three posts; for a Pi on a host cable, fit it without the cable |

**Changing cells.** Undo the thumbscrew under the grip by hand and pull the
drawer out. Change the cells, push it home and tighten the thumbscrew. Its
contacts meet the springs as it goes home: no tool, no wire to unplug. It
only goes in one way round.

**Charging the 18650.** Turn the switch off and plug a USB-C charger into
the port in the drawer's base. The charger's LEDs show through a window in
the grip's front.

**Cell safety.** Use a protected 18650 (a button-top cell up to 70 mm), or
rely on the charger's DW01 protection. Mind the polarity marks in the
holders. NiMH cells in series should not be run flat.

## The hub and its leads

Every module meets the hub by one lead with a JST-XH plug at the hub's end,
so any one of them can be unplugged and tested on its own. The battery and
trigger leads plug in from below, out of the grip's bore. The 5 V and GND
test pins are behind the left receiver cover. Each lead's length is the
build's (the bill of materials lists each for its configuration); the
battery, trigger and feedback leads are at most 60 mm.

| Lead | From | At the hub | Ways |
| --- | --- | --- | --- |
| battery lead | the grip's spring contacts | JST-XH 2 | + and - from the cells |
| trigger lead | the switch | JST-XH 2 | the switch and GND |
| feedback lead | the feedback carrier | JST-XH 4 | see Feedback |
| buttons lead | the button panel | JST-XH 3 | GPIO4 (Start, pin 7), GPIO10 (Select, pin 19), GND |
| board lead | the ESP32-CAM, header row +1 pins 1-6 | JST-XH 6 | 5V, GND, IO12, IO13, IO15, IO14 |
| debug lead | the ESP32-CAM, header row -1 pins 3-8 | (the debug board) | IO0 to BOOT, GND, VCC not connected, U0R to RX, U0T to TX, GND |
| Pi signal lead | the Pi's header, odd pins 1-19 | JST-XH 10 | pin 1 3V3, 3 SDA, 5 SCL, 7 GPIO4, 9 GND, 11 GPIO17, 13 GPIO27, 15 GPIO22, 17 3V3, 19 GPIO10 |
| Pi power lead | the Pi's PWR port | JST-XH 2 | 5V and GND |

GPIO4 and GPIO10 are free unless 1-Wire or SPI is enabled on the Pi.

## Feedback

One optional carrier on the receiver's right rails, next to the hub. All
three fit the same place; changing the device changes only the carrier and
its lead. Without one, `spacer-40` takes its place. Each driver's input has
a 10 k pull-down, so a device never runs at power-up or with today's
software, and GPIO12 (one of the ESP32-CAM's boot-strapping pins) stays low
at boot. Nothing drives them yet.

| `feedback` | Device | Driver | Pins |
| --- | --- | --- | --- |
| `vibration` | A 10 mm coin motor, from the hub's 5 V | A transistor driver, its board holding the motor in its ring | Pi GPIO22 (pin 15); ESP32-CAM GPIO12 |
| `solenoid` | A 5 V push-pull solenoid, from the cells after the switch, kicking into an anvil on its own carrier | A MOSFET module with a flyback diode | Pi GPIO22 (pin 15); ESP32-CAM GPIO12 |
| `lra` | A 10 mm coin LRA | A DRV2605L at I2C address 0x5A, from the board's 3.3 V | Pi I2C1, pins 3 and 5; ESP32-CAM GPIO14 (SDA) and GPIO15 (SCL) |

The solenoid is refused on the USB tether, which has no cells. To bench
check a motor or solenoid carrier, touch its drive line to the hub's 5 V
test pin: it runs while touched and stops when released.

## Skins

The look is a set of covers over the bones: a left and a right half for the
receiver, for each barrel and for the grip, and a ring at the muzzle. Every
cover section ends on a line of port bolts, so each port's bolts clamp the
covers either side of it; the grip's covers come up the receiver's flank to
meet the receiver's at the grip bolt. Changing style means changing covers
only; nothing inside moves, so the gun keeps its zero. Accent parts print
separately, in a second colour, and are trapped between a cover and the
bone: no glue.

| Style | Parameter | Default | Range | What it does |
| --- | --- | --- | --- | --- |
| `minimal` | `shroud_length` | 0 | 0 to 20 | How far the muzzle ring reaches past the muzzle (mm) |
| `minimal` | `chamfer` | 1.2 | 0.4 to 2 | The 45-degree chamfer on every outer edge (mm) |
| `minimal` | `grip_texture` | `grooves` | `grooves`, `none` | Shallow grooves across the grip's flanks |
| `blaster` | `shroud_length` | 16 | 6 to 30 | The flared muzzle ring's length (mm) |
| `blaster` | `fin_height` | 7 | 0 to 12 | The dorsal fin's height over each barrel (mm); 0 removes it |
| `blaster` | `chamfer` | 2 | 1 to 2.2 | The faceting chamfer (mm) |
| `blaster` | `accents` | true | true, false | A stripe down each side of the receiver, as separate parts |

Set them in `[style]`. A value outside its range is refused, naming the
parameter and the range. Every value inside it builds covers that pass
every check.

### Designing your own skin

Every build writes the skin interface to `interface/`:
`skin-interface.step` (open it in FreeCAD, Fusion, Onshape or any CAD
tool) and `skin-interface.json` (the same, as numbers). Coordinates are the
gun's, in mm: x forward along the camera axis, y to the gun's left, z up.

- **Core envelope.** The solid named `core envelope` is the core's outside.
  A cover may touch its surface, never enter it: no hook, tab or peg holds
  a cover, only the bolts.
- **Bolts.** Every through-bolt is a named solid, with the flange a cover
  must have there: 3 mm, with a 3.4 mm clear hole, on each side. On the
  right, the cover carries a hex pocket for the M3 lock nut, 5.5 mm across
  flats and 2 mm deep from its outer face. They are `rear port bolt upper`,
  `rear port bolt lower`, `receiver port bolt upper`,
  `receiver port bolt lower`, `barrel 1 port bolt upper`,
  `barrel 1 port bolt lower`, `barrel 2 port bolt upper`,
  `barrel 2 port bolt lower` (a long gun), `grip bolt` and `backstrap bolt`.
- **Keep-out zones.** No cover may enter any of these named solids:
  `view ov2640`, `view cm2`, `view cm3` (each camera's field of view);
  `trigger` (its travel, the finger's room, the stop screw's and the
  trigger bolt's access from below); `switch, LEDs and buttons` (the power
  switch, the LEDs and the Start and Select buttons on the left side);
  `rear cap removal`; `drawer and thumbscrew` (everything under the grip's
  base); `charge indicator` (the 18650 charger's LEDs); `window and plugs`
  (under each barrel: the Pi's plugs, cables and clamp); `vents` (the
  Pi's vent); `nose top` (the ESP32-CAM's debug socket, BOOT button and
  light guide); `camera and nose removal` (their way out forward); and
  `bolt access` (each bolt's head and hex key, and each nut).
- **Antenna zones.** `antenna esp32-cam` and `antenna pi-zero-2w` reach 10
  mm round each board's antenna. A plastic cover may pass through them; a
  metal or metal-filled one may not.
- **Print rules.** Covers print flank down: give each half a flat outer
  flank, no downward face steeper than 45 degrees from vertical, and no
  bridge longer than 10 mm.

Then check your parts, exported as STL or 3MF in the interface's
coordinates (add `--metal` for metal or metal-filled parts):

    uv run boresight-case check-skin my-gun.toml left.stl right.stl

It reports each part as conforming, or every violation with the zone or
bolt it breaks.

## Printing

Print the fit coupon first (`boresight-case coupon`, under 10 g and a few
minutes). Push its tenon into each socket. The dots by the one it slides
into without play give the clearance (1 dot 0.15 mm to 5 dots 0.35 mm):
set `clearance` in `[printer]`. The nut pocket that grips a nut without
forcing it gives `interference` (1 dot 0, 2 dots 0.05, 3 dots 0.10). Try
the round pegs in a Pi's mounting hole, and the tab in the carrier slot,
the same way. Then build and print the gun.

Parts are exported already lying in their print orientation: drop them in
the slicer and do not rotate them. Every part fits a 180 x 180 x 180 mm
bed (set another in `[printer] volume`, and the build refuses any part
that does not fit). Every part prints without support: turn supports off.

| Parts | Material | Settings |
| --- | --- | --- |
| Trigger housing, blade, plunger, switch plates | PETG | 4 perimeters, 40-60% infill |
| Receiver, barrels, grip, rear cap | PLA or PETG (PETG if it may get warm) | 4 perimeters, 25-30% infill |
| Kits, hub, carriers, drawers, spacers | PLA or PETG | 2-4 perimeters, 20-40% infill |
| Covers and accents | PLA or PETG | 3 perimeters, 15-20% infill |

The bill of materials (`bom.md`) gives each part's settings, and every
lead's plugs, pins and length. Use a 0.4 mm nozzle and 0.2 mm layers.

**Without Python.** CI builds every shipped configuration on each push
and keeps them as one downloadable artifact, `case`: open the
repository's Actions tab, pick a run of the CI workflow and download it.
It is a parts library: `parts/` holds every distinct part's STL and 3MF
once, `step/` their STEP files, `interface/` the skin interface, and
`configurations/<name>/` each configuration's bill of materials (which
names the files in `parts/` to print) and exploded view. Configurations
are named board, drawer, mechanism and switch, and style, then whatever
differs from one barrel, no feedback and no buttons, like
`esp32-cam_aa_bolt-mx_minimal` or `pi-cm3_18650_button-microswitch_blaster_long_lra`.

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
  nothing missing and no bolt or nut over (*Shopping for an AA ESP32-CAM gun*)
- [ ] The LRA carrier wires up from the bill of materials alone (*Wiring
  the LRA*)
- [ ] A CI run's artifact for a configuration holds everything to print it
  (*Printing without Python*)

**Bones, bolts and teardown**

- [ ] Dropped from 1.5 m onto a hard floor on its muzzle, its side and its
  grip base, a PLA gun has nothing come off or loosen (*A drop onto a hard
  floor*)
- [ ] The receiver's port bolts hold the barrel and both sections' covers
  (*One bolt does three jobs*)
- [ ] With the drawer out, the grip and its covers stay tight (*Changing
  the drawer leaves the grip tight*)
- [ ] A second barrel goes on with the camera module moved forward and two
  more bolts (*From standard to long*)
- [ ] With no barrel, the nose in the receiver's port, the gun aims and
  fires (*A compact gun*)
- [ ] A bone taken out has nothing bought attached (*A bare bone*)
- [ ] The feedback carrier moves into a barrel's rails and is held there
  (*Moving a carrier*)
- [ ] The barrel comes off with its own modules inside (*Taking the barrel
  off*)
- [ ] A tenon offered upside down hits the key rib first (*Nothing goes in
  upside down*)
- [ ] With no covers, on spacer collars, every part is held and the gun
  aims and fires (*Bench test without skins*)
- [ ] A long gun comes apart and goes back with only the 2.5 mm hex key and
  at most 12 bolts (*A full teardown and rebuild*)
- [ ] Twenty rebuilds, and every joint still tightens fully (*Twenty
  rebuilds*)
- [ ] An hour of the solenoid at one kick a second turns no nut (*An hour
  of feedback*)
- [ ] The trigger module comes out by its bolt and its plug, nothing cut or
  desoldered (*Removing the trigger cassette*)
- [ ] An ESP32-CAM gun on the AA drawer converts to the Pi kit with only
  the kit's parts changed (*Converting an ESP32-CAM gun to a Pi gun*)

**Board kits**

- [ ] The ESP32-CAM reflashes with the nose off, every header pin
  reachable (*Flashing without unsoldering*)
- [ ] A USB-serial adapter on the nose's socket reads the log of a running
  gun (*Reading the log*)
- [ ] Holding BOOT while switching on, the board flashes through the socket
  and runs the new firmware after a power cycle (*Flashing in place*)
- [ ] Both Camera Modules sit on the same standoffs, facing forward
  (*Either camera module fits*)
- [ ] The micro-SD card comes out with only the barrel off (*Swapping the
  SD card*)
- [ ] A mini-HDMI cable goes straight into the Pi at the window, covers on
  (*Plugging into a TV*)
- [ ] A hard pull on the HDMI cable leaves its plug seated, the clamp
  holding (*A tug on the cable*)
- [ ] A Pi on the 18650 drawer boots and runs from the cell (*A Pi on the
  18650 drawer*)
- [ ] A Pi on a host cable, the tether drawer fitted without its cable,
  runs as a USB gun, the hub's LEDs and the trigger working (*A Pi on a host
  cable*)
- [ ] After 30 minutes of aiming, the Pi's processor is within 10 C of the
  same board in open air: in case ____ C, open air ____ C, heatsink ____
  (*Temperature after a long session*)
- [ ] A frame captured through the muzzle shows no part of the case in any
  corner, for each camera (*No vignetting*)
- [ ] The trigger and status LED work on the default settings, on both
  kits (*No software change*)
- [ ] The status LED is visible while aiming (*Checking the solve state
  while aiming*)
- [ ] With the buttons and console mode configured, Start reaches the game
  and the trigger still works (*Starting a game*)
- [ ] The ESP32-CAM's Wi-Fi range inside the case is enough at the
  distance you play from: ____ m

**Power**

- [ ] The 18650 drawer replaces the AA drawer, locked by its thumbscrew,
  nothing else changed (*Changing battery type*)
- [ ] A drawer offered the wrong way round does not enter far enough to
  touch the contacts (*A reversed drawer does not go in*)
- [ ] AA cells change by hand, no tool or unplugging (*Swapping AA cells*)
- [ ] The hub's test pins read 4.75-5.25 V with only the left receiver
  cover off (*Testing the supply*)
- [ ] Any one plug pulled from the hub leaves the rest working (*Taking one
  module out of the circuit*)
- [ ] Four NiMH cells at 1.0 V each keep a streaming ESP32-CAM within 4.75
  to 5.25 V (*Nearly flat NiMH cells*)
- [ ] And a Pi aiming with HDMI and the motor running: ____ V (*The Pi at
  full load*)
- [ ] With the switch off, the gun draws nothing from the cells
  (*Switching off*)
- [ ] The 18650 charges through the drawer's base with the switch off, its
  LED visible (*Charging overnight*)
- [ ] Run down, the 18650 is cut off by its protection (*Running the cell
  down*)

**Trigger**

- [ ] Pulled with the index finger, the blade moves back toward the palm
  and the switch actuates (*Pulling with the index finger*)
- [ ] An MX-style switch snaps into its plate and the trigger actuates it
  (*Fitting an MX-style switch*)
- [ ] The microswitch plate swaps in with the mechanism and lead unchanged
  (*Changing to a microswitch*)
- [ ] A hard pull or press ends on the stop screw, past actuation, with
  either plate and both mechanisms (*A hard pull*)
- [ ] The trigger returns and releases on every pull (*Release with a light
  microswitch*)
- [ ] The button, with the MX plate, actuates the switch and moves as far
  as it does (*A button instead of a lever*)
- [ ] A 50 N pull at the blade moves nothing in the pocket: ____

**Feedback**

- [ ] The vibration carrier swaps for the solenoid's, the lead into the
  same socket (*Changing the vibration motor for the solenoid*)
- [ ] A carrier slid in with its spacers cannot move once the barrel is
  bolted back (*Fitting a carrier*)
- [ ] The solenoid pulsing on four NiMH cells keeps the Pi running within
  4.75-5.25 V (*A kick while the Pi aims*)
- [ ] The LRA's driver answers at 0x5A on I2C bus 1, its lines idling at no
  more than 3.3 V (*The LRA driver on the Pi's bus*)
- [ ] The motor runs on a Pi on a host cable (*A vibration motor on a Pi
  on a host cable*)
- [ ] No device runs at power-up with today's software (*Power-up with
  today's software*)
- [ ] Touched to the 5 V test pin, a carrier's drive line runs it
  (*Bench check of a carrier*)
- [ ] 200 kicks leave the aim, every nut and the carrier where they were
  (*Many kicks*)

**Covers**

- [ ] Changing style touches only covers and their bolts (*Changing style
  on an assembled gun*)
- [ ] Each cover's holes line up with the bolts (*A skin's screws line
  up*)
- [ ] The drawer comes out with the covers on (*Battery swap with skins
  on*)
- [ ] HDMI plugs in with the covers on (*Plugging HDMI with covers on*)
- [ ] Accent parts printed in a second colour are held without glue (*A
  two-colour gun*)
- [ ] After a restyle the aim point is unchanged (*Restyling keeps the
  zero*)
