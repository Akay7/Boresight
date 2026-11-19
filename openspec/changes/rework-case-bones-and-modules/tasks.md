# Tasks

## 1. Configuration and validity rules

- [x] 1.1 Add the `barrels` (0, 1, 2; default 1), `feedback` (`none`, `vibration`, `solenoid`, `lra`) and `buttons` (bool) keys, and make `mechanism` accept `bolt` and `button` only. Verify with tests:
  - `mechanism = "filament"` is refused with a message naming `bolt` as its replacement;
  - the defaults build a standard ESP32-CAM gun.
- [x] 1.2 Implement the validity rules from the case-modules "Which configurations are valid" requirement: the Pi kit takes any drawer and at least one barrel; the solenoid is refused on the tether; the buttons are allowed on the Pi kit only. Verify with tests, one per rule, that each refusal happens before any geometry is built and names the parts and the reason, and that a Pi plus 18650 plus one barrel configuration is accepted.
- [x] 1.3 Generate the shipped set from the rule in design.md ("Configuration and the shipped set"). Verify a test that asserts the exact count, that every member is valid, and that the full board × drawer × mechanism × plate × style set at one barrel is included.

## 2. Purchased parts

- [x] 2.1 Add envelopes to `vendor.py`, each with a source:
  - fasteners: M3 × 50 and M3 × 12 socket-head bolts, M3 nylon-insert nuts, washers, the M3 thumbscrews;
  - power and controls: the 1.5 A buck-boost module, the LM66100-class ideal-diode module, the slide switch, the LEDs, two tactile buttons;
  - connectors: JST-XH 2-, 3- and 4-pin sockets and plugs, 1×6 and 1×10 Dupont housings, the 6-pin female header;
  - Pi cables and parts: right-angle micro-USB, mini-HDMI and micro-USB plug heads, the 38 mm Pi Zero camera ribbon, the 14 × 14 × 6 heatsink;
  - feedback parts: the 10 mm coin motor with its transistor driver, the 5 V push-pull solenoid with its MOSFET module and diode, the 10 mm LRA with its DRV2605L board.

  Verify the existing vendor tests: every envelope is a closed solid and every entry has a source.
- [ ] 2.2 Measure and add the Pi Zero 2 W's PCB antenna region and the ESP32-CAM's light-guide LED position to `vendor.py` from the boards' drawings or a caliper. Verify a test that both boards' antenna regions are defined as solids the antenna check can use.

## 3. Interfaces

- [x] 3.1 Redefine the module joint in `interfaces.py` and `joints.py` as the port:
  - a 31 × 45 opening, 12 mm deep, with the key rib;
  - two through-bolt positions at x = mouth − 6, z = ±12;
  - each bolt yielding the bone's holes, the filler's crush tube, the left cover's flange hole and the right cover's nut pocket from one definition.

  Verify tests that a tenon and a port mate with the configured clearance, the bolt holes line up through every layer, and the clamp stack is 46 mm on the body.
- [x] 3.2 Define the rails on both inner walls (C-channels at z = +19.5 and −14.5 for a 2 mm plate, 34 mm tall) and a carrier-plate and spacer generator that fills a run to length. Verify tests that a carrier slides in from either open end with the configured clearance, and that the generated spacers fill each bone's run to within the clearance.
- [x] 3.3 Define the grip's two through-bolts (the joint and the backstrap boss, both clear of the drawer bay) and the trigger pocket with its bolt from below. Verify tests that neither grip bolt crosses the bay and that the pocket's housing mates with the configured clearance.

## 4. Bones

- [x] 4.1 Rebuild the receiver:
  - two ports, rails on both walls and the grip socket;
  - the hub switch's slot in the left wall;
  - side windows with 45° ends between the rails and the bolt bands;
  - no trigger well.

  Verify tests that it passes bed fit and the overhang check, and that it carries no purchased part.
- [x] 4.2 Rebuild the barrel:
  - a tenon, a port and rails on both walls;
  - the floor window at x 14…68 with edge ribs;
  - vent slots in the right wall over the Pi's processor position;
  - side windows.

  Verify bed fit (standing on the muzzle), the overhang check, and that the same barrel file serves the first and second barrel.
- [x] 4.3 Rebuild the grip (a tenon with its through-bolt, the drawer bay, the trigger pocket, the backstrap boss and the thumbscrew's nut) and the rear cap (a 12 mm tenon, no electrical parts). Verify bed fit, overhang and the core assembly's interference check for 0, 1 and 2 barrels.
- [x] 4.4 Update the module overview in `hardware/case/README.md` with bones, modules and covers, the port and the steel-only rule. Verify the docs test that every part named in the README exists in the build listing.

## 5. Steel-only and clearance checks

- [x] 5.1 Add the bolts-versus-what-works check: each bolt's swept cylinder plus 0.5 mm against every module, lead path and camera frustum. Verify unit tests that a bolt moved across the Pi sled fails naming the bolt and the sled, and that the shipped set passes.
- [x] 5.2 Extend the antenna check to every metal part (bolts, nuts, the thumbscrews, cells, the hub's parts, the feedback devices) against a 10 mm offset of each board's antenna. Verify a test that moving the muzzle-port bolts within 10 mm of the ESP32-CAM antenna fails naming the bolt, the board and the zone.
- [x] 5.3 Replace the teardown-screw count with a bolt count and length check, at most 12 bolts in two lengths; thumbscrews do not count. Verify tests that a standard gun counts 9, a long gun 11 and a compact gun 7, all M3 × 50 or M3 × 12.
- [x] 5.4 Open check: confirm in the model that the Pi Zero 2 W's antenna is at least 10 mm from the nearest bolts (the barrel's rear port at x −6 and the muzzle port at x 94). Verify the antenna check passes for every Pi configuration; if it does not, move the sled and record the new position in design.md.

## 6. Trigger in the grip

- [x] 6.1 Rebuild the trigger as a grip module:
  - the housing in the pocket, with a bolt from below;
  - the blade on an M3 bolt pivot, its tail above the pivot onto the switch plate;
  - the stop screw and the return spring;
  - the button mechanism adapted to the same housing.

  Drop the filament-pin parts and the old cassette under the receiver. Verify the trigger tests for both mechanisms and both plates: travel to actuation, the over-travel stop and the spring return.
- [x] 6.2 Verify a test that the reach from the grip's back to the blade's face is 60–70 mm, and that the blade's swept travel is clear of the grip, the frame cover and the trigger guard.

## 7. Drawers

- [x] 7.1 Replace each drawer's printed latch with a captive M3 thumbscrew in its base into the grip's nut, and allow PLA in the print list. Verify tests that every drawer still passes the bay's key and interference checks, the thumbscrew clears the bay's contacts, and a reversed drawer still stops before contact.

## 8. Hub

- [x] 8.1 Model the hub carrier:
  - the regulator, the ideal diode and the slide switch, whose knob passes the receiver's slot;
  - the power and status LEDs;
  - the JST-XH sockets, the Dupont lead seats and the 5 V and GND test pins;
  - the solenoid supply tap.

  Place it at x −92…−52 on the receiver's rails. Verify the interference check, and that the switch knob and LEDs sit in the left cover's keep-out openings.
- [x] 8.2 Add the wiring table (lead, from, to, plug, pins, length) as data the build writes into the bill of materials. Verify tests that the battery, trigger and feedback leads are at most 60 mm and that every module in a configuration has exactly one lead to the hub.
- [x] 8.3 Document the hub's wiring in `hardware/case/README.md`, including the Pi signal lead's pin table from design.md and the Start and Select pins (GPIO4, GPIO10). Verify the docs test that every lead in the wiring table appears in the README.

## 9. Pi kit

- [x] 9.1 Model the Pi sled in the barrel:
  - the PCB at x 8…73 with its ports down, the SD card at the rear;
  - the Pi camera module in the muzzle port, with crush tubes for both port bolts;
  - the 38 mm ribbon path;
  - room for the heatsink under the vents.

  Verify the interference check and that the SD card is reachable with the barrel off.
- [x] 9.2 Model the window's plugs as bought parts (right-angle mini-HDMI, the micro-USB data plug and the right-angle PWR plug), the PWR lead's path to the hub, and the clamp bar with its captive thumbscrew. Verify tests that every plug reaches its port through the window with covers fitted, and that shortening the window fails the check naming the plug.
- [x] 9.3 Open check: measure in the model the gap between the Pi camera board's edge and the muzzle-port bolts' crush tubes, expected about 1 mm. Verify a test asserting at least 0.5 mm. If it is less, move the Pi camera module's bolts to z = ±16, update the port definition for that module, and record it in design.md.
- [x] 9.4 Update `deploy/pi/README.md` and the root README's case section: cables plug in under the barrel, any battery drawer works, a host cable goes into the window with the tether drawer fitted without its cable, and the heatsink. Verify the README links resolve and the docs test passes.

## 10. ESP32-CAM nose

- [x] 10.1 Model the nose:
  - a tenon in the muzzle port with crush tubes for both port bolts;
  - the board's back at x 124, with the capacitor seat;
  - the two 1×6 housings on the header;
  - the debug socket and BOOT button on its top, clear of the antenna;
  - the light guide from GPIO33's LED to a window on the nose's top.

  Verify the interference check, the antenna check, and that the housings clear the port bolts by at least 2 mm.
- [x] 10.2 Support the compact build (the nose in the receiver's front port, no barrel). Verify a test that the compact ESP32-CAM gun builds and passes every check, and that its length is within 5 mm of 142 mm.
- [x] 10.3 Update the root README's flashing section: the debug socket on the nose's top, the FTDI-order pinout, BOOT plus power-on to flash, and VCC left unconnected. Verify the docs test and that the README's pin names match the header table in `vendor.py`.

## 11. Feedback carriers

- [x] 11.1 Model the three carriers (motor plus driver, solenoid plus MOSFET module, diode and printed anvil, LRA plus DRV2605L) and the no-feedback spacer, on the receiver's rails between the hub and the front port. Verify the interference check for each carrier with each board, and that each lead is at most 60 mm.
- [x] 11.2 Record each carrier's pins (Pi GPIO22 or I2C1, ESP32-CAM GPIO12 or GPIO14 and GPIO15) and the driver pull-downs in the wiring table and the README. Verify a test that no feedback pin equals a trigger, LED or button pin for either kit.

## 12. Start and Select buttons

- [x] 12.1 Model the button panel on the left side next to the switch, and its lead through the hub to the Pi signal lead's GPIO4 and GPIO10. Verify the interference check, that the buttons sit in the left cover's keep-out openings, and that a configuration with buttons on the ESP32-CAM kit is refused.

## 13. Covers

- [x] 13.1 Rebuild the `minimal` and `blaster` styles on the through-bolt positions: 3 mm flanges, left-side holes and right-side nut pockets, no hooks. Add barrel covers for each barrel, the lower barrel cover's window opening and the nose's muzzle cap. Capture the accent parts under bolts or between a cover and a bone. Verify the skin tests: every style fits every shipped configuration, and no skin enters a keep-out zone.
- [x] 13.2 Add the new keep-out zones: the window and its plugs, the clamp, the nose's socket and button, the switch, the buttons, the LED windows, the drawer thumbscrew and the antenna metal zone. Verify a skin-check test for each zone that a part entering it fails naming the zone.
- [x] 13.3 Update the skin interface output (bolt positions, axes and flange thickness) and the third-party skin check, so that a part with a hook or a hole of the wrong flange thickness fails. Verify `check-skin` tests for a conforming skin and for each failure.
- [x] 13.4 Add the spacer collars for building without covers. Verify a test that a coverless build uses the same bolts and passes every check.

## 14. Outputs and CI

- [x] 14.1 Extend the bill of materials with the bolts by length, the nuts, the thumbscrews, the hub's parts, the feedback parts and every lead from the wiring table. Verify the BOM tests: an AA ESP32-CAM gun lists every bolt and nut with none left over, and the LRA wiring names pins 1, 3 and 5.
- [x] 14.2 Run `uv run boresight-case build --all --out dist` and the full test suite. Verify both pass, each distinct part is written once, and the build time is recorded in design.md if it grew past today's.

## 15. Hardware verification

- [ ] 15.1 Print and assemble a standard ESP32-CAM gun and a standard Pi gun in PLA. Verify the drop test (1.5 m onto a hard floor: muzzle, side, grip base) leaves no part loose, and record the results in the README's checklist.
- [ ] 15.2 Bench-check the hub. Verify:
  - the Pi at full load stays within 4.75–5.25 V on 4 × NiMH at 1.0 V per cell;
  - a Pi on a host cable powers the hub with no back-feed into the regulator;
  - the solenoid pulsing does not drop the Pi's supply.
- [ ] 15.3 Measure the trigger (a 50 N pull at the blade, no movement in the pocket) and the feedback (200 solenoid kicks and an hour at one per second leave the aim and every nut unchanged). Verify by recording the measurements in the README.
- [ ] 15.4 Run the Pi aim pipeline for 30 minutes in the closed case and in open air. Verify the in-case processor temperature is at most 10 °C higher, and record which heatsink was used.
- [ ] 15.5 Flash an ESP32-CAM in place through the socket on the nose's top with BOOT held, and read its log. Verify the board runs the new firmware after a power cycle.

## Workflow follow-up

- Archive `add-modular-gun-case` before archiving this change: this
  change's deltas modify its specs, and archive refuses them until those
  specs exist.
- Archive this change after its tasks are done.
