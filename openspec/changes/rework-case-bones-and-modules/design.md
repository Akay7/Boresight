# Design

## Context

See proposal.md for why. The design canvas
(https://claude.ai/artifact/UHFBkBsBmPUsnoSavuyHBN) is the visual
reference for every decision below. Its boards are named here in
quotes, for example "Four connections".

Today `hardware/case/` builds the case from `add-modular-gun-case`:
- **Bones and ports.** The receiver and barrel are 36 × 50 mm tubes with
  2.5 mm walls, both printed standing. Joints are a 31 × 45 tenon, 12 mm
  deep (8 for the rear cap), held by one M3 across.
- **Trigger.** A cassette hangs under the receiver at x −48…−14.
- **Pi.** The Pi rides a sled on C-channels on the receiver's left wall.
- **Power.** The regulator and the switch live in the rear cap.
- **Skins.** Hooks plus one M3 × 8 per skin.
- **Shipped set.** 72 configurations.
- **Bed.** Every part fits a 180 mm cube.

Most of this survives; the joints, wiring and the board's position move.
Coordinates below are the model's: x forward, z up, mm, bore on the x
axis, and the receiver from −100 to 0.

## Goals / Non-Goals

**Goals:**
- One port definition, used by every bone end and every module that plugs
  into one, so the gun can be rearranged without new interfaces.
- Steel carries every load that keeps a part on the gun. PLA only takes
  compression.
- Every lead short and pluggable, and every board debuggable without
  opening the gun.
- Checks for everything new that a computer can check: bolt clearances,
  antenna zones, the plugs at the window, bed fit, supports, the bill of
  materials.

**Non-Goals:**
- Firmware or software changes. Feedback and the Start and Select buttons
  are wired, but nothing drives them yet.
- Covers in detail beyond rebuilding today's two styles on the new bolt
  positions. New styles, such as the heavy slab look on the canvas, are a
  later change.
- Other boards, a battery gauge, charging AA or AAA cells in the gun.

## Decisions

### Steel only: through-bolts, crush tubes, lock nuts

Each port takes two M3 bolts 6 mm in from its mouth, at z = ±12. Each
passes through the left cover's flange, the bone, the tenon or module,
the bone and the right cover's flange. A nylon-insert nut sits in a hex
pocket in the right cover. Every through-bolt is M3 × 50:
- the body is 36 mm, plus two 3 mm cover flanges, plus a 4 mm nyloc, so
  the clamp length is 46 mm;
- the grip is 37.2 + 6 + 4 = 47.2 mm.

The trigger's bolt is the only other length, M3 × 12.

**Crush tubes.** Between the walls, the clamp load goes through a printed
crush tube. The tube is part of whatever fills the port: the tenon, the
camera module or the nose. So the bolt squeezes a solid stack, not a
hollow box.

**Bench builds.** With no covers, 3 mm printed spacer collars stand in
for the flanges, so the same bolts work.

**Bolt count.** A standard gun has eight bolts:
- two at the rear cap port;
- two at the barrel port;
- two at the muzzle port;
- one across the grip joint;
- one through a boss on the grip's back, below the bay.

The trigger's bolt makes nine. A long gun adds two (eleven); a compact
gun has two fewer (seven).

*Alternatives:*
- **Printed hooks (today's skins), then printed dovetail rails.**
  Rejected by the user: in a fall a printed retaining feature breaks or
  lets go.
- **Magnets.** Tool-free, but a dropped gun sheds its covers.
- **Heat-set inserts per cover.** Steel, but they need many more
  fasteners. A through-bolt holds two bones and two covers at once.

### One port, every end

The port is the existing joint, made uniform:
- a 31 × 45 opening, 12 mm deep, with the key rib under the top wall;
- two bolt holes at x = mouth − 6.

The rear cap's tenon grows from 8 to 12 mm. The camera modules plug
into a port like a tenon. Nothing else changes in the tube section, so
the parts' print orientation and bed fit stay as they are.

### Bones carry only connections

- **Receiver:** two ports, rails on both walls and the grip socket in its
  floor.
- **Barrel:** a tenon, a port, rails, and the window in its floor.
- **Grip:** a tenon, the drawer bay, the trigger pocket and the backstrap
  boss.
- **Rear cap:** a tenon and a plate.

**Windows.** Side windows sit between the rails and the bolt bands. They
have 45° ends, so they print standing with no supports ("The bones").
The top and bottom bands, the rails and the port rings carry the load.

**The barrel repeats.** The second barrel of a long gun is the same file.

### Rails and carriers

The receiver's existing C-channels are mirrored onto the right wall and
copied into the barrel: z = +19.5 and −14.5, holding a 2 mm plate edge.

**Carriers.** The hub, the Pi sled and the feedback devices are all
carriers.

**Holding them.** A carrier is held lengthwise by the tenon or module in
the next port and by printed spacers that fill the rest of the run.
Spacers are cut to length per configuration by the build.

**One bone each.** No carrier spans a joint. Every bolt sits in a port
zone, the outer 12 mm at each end, so it never crosses a carrier.

### Trigger in the grip

**Pocket.** The grip's front grows a pocket at its top, where it meets
the receiver's floor. The trigger module's housing fits the pocket and
is held by one M3 × 12 from below into a nut. Its front part reaches
forward under the receiver.

**Blade and switch.** The blade hangs from a pivot at z ≈ −35.5; the
lever's pivot is the M3 bolt. The blade's tail rises above the pivot.
When the finger pulls the blade back, the tail swings forward onto the
switch plate.

**Switch plates.** MX or microswitch. They mount in the housing's front,
facing back.

**Stop and spring.** The stop screw and return spring stay as today.

**Mechanisms.** The button mechanism keeps its plunger and cap, pressing
the same plate. The filament-pin pivot is dropped, because a plastic pin
would be the one non-steel pivot.

**Reach.** From the back of the grip to the blade the reach is about
65 mm ("End result").

*Alternative:* keeping the cassette under the receiver. Rejected: the
trigger then sat far ahead of the hand, and the cassette needed its own
screw into the receiver.

### Pi in the barrel, cables at the window

**Placement.** The sled sits at x 4…83.5 in barrel coordinates, with the
Pi's PCB at 8…73 and its port edge facing down. The ports are at:
- mini-HDMI x 20.4;
- USB data x 49.4;
- PWR x 62.

The window in the barrel floor is x 14…68. The Pi camera module fills
the muzzle port, with its PCB at x 88.5, and the 38 mm Pi Zero ribbon
spans the gap. The micro-SD faces the barrel's rear end. In a long gun
the Pi sits in the last barrel.

**Cables.**
- **HDMI and USB:** plug straight up into the Pi; no cable runs inside.
- **PWR:** a right-angle micro-USB plug, its lead running back along the
  floor to the hub.

**Cable clamp.** A clamp bar under the window, held by one captive M3
thumbscrew into a nut, grips the cables just below their plugs. It is
not counted as a teardown bolt, since it turns by hand.

**Cooling.** Vent slots in the barrel's right wall and the right cover
sit over the processor. There is room for a 14 × 14 × 6 heatsink. The
window also breathes.

*Alternatives:*
- **Pi in the receiver, HDMI to the rear cap.** That is the previous
  draft. It needs a long internal cable, a strain relief in the cap and a
  long camera ribbon.
- **Ports facing sideways.** Cables in the off hand's way.

### ESP32-CAM in a nose

**Nose.** The nose module's tenon fills the muzzle port and takes the
port's two bolts with its own crush tubes. Its body continues the 36 × 50
section forward to x ≈ 136. The board's back sits at x 124, 24 mm out
front.

**Why 24 mm.** The two 1×6 Dupont housings on the board's own pins reach
23 mm back (6 mm pins, 2.5 mm header, 14.5 mm housing). At this position
they clear the port bolts by about 3 mm.

**Antenna.** It sits at x 124…129, z 14.25…20.25, about 30 mm from the
nearest bolt and outside the tube.

**Muzzle cap.** The cap is a cover over the nose; its lens opening
follows the camera.

**Plugs on the header.** The header rows are those in `vendor.py`.
- **Row +1, pins 1–6** (5V, GND, IO12, IO13, IO15, IO14) carry power,
  the trigger and feedback to the hub.
- **Row −1, pins 3–8** (IO0, GND, VCC, U0R, U0T, GND) go to the debug
  socket.

**Debug socket.** A 1×6 female header and a tactile BOOT button under
the nose. The socket's pins are GND, nc, nc, RX (U0R), TX (U0T), nc.
This follows the FTDI order, so a common adapter plugs in directly. VCC
stays unconnected, and the gun powers the board.

**Status LED and capacitor.** A light guide carries the on-board red LED
(GPIO33) to a window on the nose's top. The 470–1000 µF capacitor sits
in the nose across 5V and GND at the plug.

**Length.** The gun is about 35 mm longer: 262 mm standard, 162 mm
compact.

*Alternatives:*
- **Board inside the muzzle port.** Its antenna would be 2 mm from the
  port bolts, and the bolts would pass through its front parts.
- **A cradle bolted 29 mm back.** Same length as the Pi gun, but it needs
  two extra holes in every barrel and breaks the "every port is the same"
  rule. The user preferred the longer nose.

### The hub

The hub is a carrier on the receiver's rails at x −92…−52, directly above
the grip, where the drawer's contacts come up through the grip's tenon.
It carries:
- **Regulator:** a 1.5 A buck-boost module set to 5.1 V.
- **Ideal diode:** an LM66100-class part on the regulator's output, so a
  Pi on a host cable can power the hub without back-feeding the
  regulator.
- **Power switch:** a slide switch. Its knob comes out through a slot in
  the receiver's left wall and the left cover, at about (−80, z 0),
  where a safety would be.
- **LEDs:** a power LED and the status LED, beside the switch.
- **Sockets:** JST-XH sockets for the battery, trigger and feedback.
- **Board connections:**
  - a 1×6 Dupont lead to the ESP32-CAM;
  - or, for the Pi, the power lead and a 1×10 signal lead.
- **Test pins:** 5 V and GND.
- **Solenoid supply:** a fused tap of the switched cell voltage, for the
  solenoid's driver.

It is built on perfboard on the carrier plate. The wiring table on
"Wiring and debugging" is the source for the leads and their lengths.

**Pi signal lead.** One 1×10 housing on the odd header pins 1–19:

| Pin | Signal | Use |
| --- | --- | --- |
| 1 | 3V3 | LRA driver supply |
| 3 | SDA | LRA driver |
| 5 | SCL | LRA driver |
| 7 | GPIO4 | Start |
| 9 | GND | |
| 11 | GPIO17 | trigger |
| 13 | GPIO27 | status LED |
| 15 | GPIO22 | motor or solenoid drive |
| 17 | 3V3 | unused |
| 19 | GPIO10 | Select |

One plug covers every Pi signal. The trigger and LED keep their default
pins. GPIO4 and GPIO10 are free unless 1-Wire or SPI is enabled, and the
README names them for `[pins] start` and `select`.

*Alternative:* a module per function wired straight to the board. That
means longer leads, more plugs on the board, and no single place to
measure.

### Feedback carriers

The three carriers (motor plus transistor driver, solenoid plus MOSFET
module plus diode, LRA plus DRV2605L) sit on the receiver's rails between
the hub and the receiver's front port, roughly x −48…−14. Each lead is
under 60 mm. Pull-downs on each driver input keep the devices off at
boot, including GPIO12's strapping requirement on the ESP32-CAM.

The solenoid kicks into a printed anvil on its own carrier, so the impulse
goes into the carrier and the rails, not the camera.

### Configuration and the shipped set

Keys:
- `barrels`: 0, 1 or 2, default 1;
- `feedback`: "none", "vibration", "solenoid" or "lra";
- `buttons`: true or false;
- `mechanism`: "bolt" or "button". The value "filament" is refused, with
  a message naming its replacement.

Validity follows the case-modules "Valid configurations" requirement.

The shipped set is:
- **Full set:** every board × drawer × mechanism × plate × style, with
  one barrel, no feedback and no buttons. That is 2 × 4 × 2 × 2 × 2 = 64.
- **Other barrel counts:** each with the default trigger and style, for
  each board and valid drawer.
- **Feedback:** each device with each board and valid drawer.
- **Buttons:** on the Pi, with each drawer.

That comes to about 100 configurations. The parts library still writes
each distinct part once, so CI's artifact grows by the new parts, not by
the configuration count.

### Checks

`checks.py` gains two checks:
- **Bolts versus what works:** each bolt's swept cylinder plus 0.5 mm
  against every module, lead path and camera frustum.
- **Antenna keep-out:** a 10 mm offset around each board's antenna
  against every metal part.

The interference check adds the window's plugs as bought parts. The skin
check rejects any skin geometry that relies on a hook. In practice it
refuses any part attached outside the published bolt positions.

## Risks / Trade-offs

- **[Bolts crush the bones]** → Crush tubes take the clamp load. The
  README says hand-tight plus a quarter turn. Nyloc nuts hold without
  more torque.
- **[PLA covers creep under the flanges]** → 3 mm flanges, a washer under
  each head, and nyloc nuts that keep their grip as the PLA relaxes.
- **[The nose takes the first hit in a fall]** → The muzzle cap covers it.
  The nose walls are as thick as the bones. The drop-test scenario covers
  the muzzle.
- **[The window weakens the barrel]** → The top, sides and both port
  rings stay closed. Ribs run along the window's edges. Measure stiffness
  against a barrel without a window in the first print.
- **[Cables lever on the Pi's ports]** → The clamp bar takes the pull,
  and right-angle plugs keep the lever arm short.
- **[A Pi on a host cable back-feeds the regulator]** → The ideal diode on
  the hub's regulator output. A bench check is a task.
- **[The trigger housing is cantilevered from the grip]** → The pocket is
  as deep as the grip wall allows, with the bolt below the pivot. A 50 N
  pull test is a task.
- **[Pi antenna and bolts]** → The Pi Zero 2 W's antenna position is not
  in `vendor.py` yet. A task measures it and the antenna check covers
  it.
- **[Pi camera board edge to the muzzle bolts]** → The drawings show about
  1 mm. A task confirms it in the model, and moves the bolts to z ±16 for
  the Pi camera module if it is less.
- **[About 100 configurations slow CI]** → The parts library builds each
  part once. Profile the build and parallelise if it exceeds today's
  budget.

## Migration Plan

1. Archive `add-modular-gun-case` once its tasks 13.1 and 14.3 are done
   or deliberately deferred. This change's deltas modify its specs.
2. Implement on a branch. The old configurations stop building: the
   `filament` mechanism and the Pi-in-receiver layout are gone. Anyone
   with a printed old case keeps it; the old CI artifacts stay
   downloadable from past runs.
3. Rollback is reverting the branch. No firmware, server or Pi software
   depends on the case.

## Open Questions

- Which 1.5 A buck-boost module ships, after a bench test on 4×NiMH at
  1.0 V per cell with the Pi at full load. The spec fixes only the
  output range and current.
- Heatsink height: 6 mm is the room allowed. Whether a lower one keeps
  the Pi within its 10 °C budget is a measurement.
