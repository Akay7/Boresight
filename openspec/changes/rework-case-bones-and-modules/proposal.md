# Proposal

## Why

The printed case from `add-modular-gun-case` works, but it is one fixed
layout. The Pi lives in the receiver, its HDMI cable would run back to the
rear cap, power sits in the rear cap, and skins hang on printed hooks.
Three things are now wanted from it:
- a Pi gun that plays on a TV by itself, on batteries;
- a feedback device;
- a gun that can be re-arranged and restyled, and that survives a drop
  when printed in PLA.

The design canvas
(https://claude.ai/artifact/UHFBkBsBmPUsnoSavuyHBN) settles a new
structure for all three. This change brings the case's specs in line with
it before any CAD work starts. It supersedes the unfinished draft
`add-case-pi-battery-and-feedback`, which assumed the old layout.

## What Changes

- **Bones, modules and covers.** The case is three layers:
  - **Bones:** receiver, barrel, grip and rear cap. They carry nothing
    bought, only connections.
  - **Modules:** everything that works. Each attaches through one
    connection.
  - **Covers:** the existing skins, which give the look and hold nothing
    up.
- **One port standard.** Every end of the receiver and barrel is the same
  port: a 31 × 45 mm opening, 12 mm deep, keyed by a rib. It takes either
  the next bone's tenon or a camera module, held by the same two M3 bolts.
  Inside, rails on both side walls take 2 mm carrier plates. The grip has
  two sockets: the drawer bay and the trigger pocket.
- **Only steel holds anything together. BREAKING:**
  - Bones, modules and covers are clamped by M3 bolts that pass straight
    through the gun, with crush tubes and nylon-insert lock nuts. A
    standard gun has eight: two at each port, one at the grip joint and
    one through a boss low on the grip's back.
  - No printed hook, slide rail, snap or flexing latch holds a part. The
    skins' hooks go. The drawer's printed latch is replaced by a captive
    thumbscrew. The filament-pin trigger pivot is dropped in favour of
    the bolt pivot.
- **The barrel repeats.** A gun has no barrel (compact), one (standard)
  or two (long). The second barrel is the same printed part.
- **The trigger moves into the grip.** The trigger module sits in a
  pocket at the top of the grip's front, held by one M3 bolt. Its blade
  turns on a pivot and is pulled back toward the palm; the blade's tail,
  above the pivot, presses the switch. **BREAKING** for the trigger
  cassette under the receiver.
- **Pi in the barrel, cables at a window.**
  - The Pi Zero 2 W rides on a sled in the barrel, right behind its
    camera, joined by a 38 mm ribbon.
  - Its ports face a window in the barrel's floor. HDMI, USB and the
    host cable plug straight into the Pi from below and never run
    through the gun.
  - A bolted clamp at the window takes any pull on the cables.
  - The Pi runs from any battery drawer, so it can play on a TV by
    itself.
- **ESP32-CAM in a nose.**
  - The ESP32-CAM rides in a nose module. Its tenon fits the muzzle port
    and is held by the port's own two bolts, and the board sits 24 mm
    out in front.
  - This keeps the antenna about 30 mm from the nearest steel and outside
    the tube. The ESP32-CAM gun is about 35 mm longer: 262 mm, or 162 mm
    compact.
  - Two 1×6 plugs push onto the board's own header pins. One goes to the
    hub; the other goes to a serial socket and a BOOT button under the
    nose, so the board can be flashed and its log read in place.
- **One hub, short leads.**
  - A hub module on the receiver's rails, right above the grip, holds:
    - the 5 V regulator, now 1.5 A;
    - the power switch, which comes out of the left side where a safety
      would be;
    - the power LED and the status LED;
    - a socket for every module's lead, plus 5 V and GND test pins.
  - The battery, trigger and feedback device sit next to it, so their
    leads are about 40 mm. The rear cap holds nothing electrical.
- **Feedback devices.** One optional carrier on the receiver's rails
  next to the hub: a vibration motor, a recoil solenoid or a haptic LRA.
  The solenoid runs from the cells after the switch, and is refused on
  the USB tether.
- **Start and Select buttons.** Two optional buttons on the left side,
  for the Pi's console mode (`add-pi-zero-nes-console`).
- **New configuration keys:** `barrels = 0 | 1 | 2`,
  `feedback = "none" | "vibration" | "solenoid" | "lra"` and
  `buttons = true | false`.
  - `mechanism` loses `"filament"`.
  - The Pi kit accepts every drawer and needs at least one barrel.
  - The shipped set is regenerated from these rules.
- **No firmware or software changes.** Every pin the case wires is a pin
  today's firmware and Pi gun software already use, or one that nothing
  drives yet: the feedback pins, and the Start and Select pins.

## Capabilities

### New Capabilities
- `case-feedback`: the gun's optional feedback devices: the carriers for
  a vibration motor, a recoil solenoid and a haptic LRA, how each is
  powered and wired, and how they stay inert until software drives them.

### Modified Capabilities
These capabilities come from `add-modular-gun-case`, which is not archived
yet. Archive it before this change: its last two tasks, 13.1 (CI run)
and 14.3 (physical print), are open.
- `case-modules`:
  - the bone, module and port structure;
  - steel-only fastening;
  - the repeatable barrel;
  - the trigger in the grip;
  - the Pi in the barrel with its window, and the ESP32-CAM nose;
  - the hub, power and wiring;
  - the debug socket and the Start and Select buttons;
  - the valid configurations;
  - the teardown rules.
- `case-fabrication`:
  - the build takes the new configuration keys;
  - the bill of materials covers the bolts, nuts, crush tubes, hub,
    leads, feedback parts and cable clamp;
  - the interference checks add the bolts, the leads and the antenna
    keep-out.
- `case-skins`:
  - covers are clamped only by the through-bolts;
  - the keep-out zones gain the window, the nose, the switch and buttons
    and the cable clamp;
  - styles fit every barrel count;
  - accent parts are held by bolts too.

## Impact

- **Code:** `hardware/case/` only, and most of it:
  - layout and joints, the port and bolt interfaces, receiver, barrel,
    grip, rear cap and drawers;
  - the trigger, now a grip module;
  - kits: the Pi sled in the barrel, the Pi camera bulkhead and the
    ESP32-CAM nose;
  - new parts: the hub, the feedback carriers, spacers, the cable clamp,
    the button panel and the spacer collars;
  - skins rebuilt on the bolt positions;
  - config, checks, the bill of materials, tests, the README and the
    shipped set.
- **Docs:** the root README's case section, `deploy/pi/README.md` (cables
  at the window, battery running) and the ESP32-CAM flashing guide (the
  socket under the nose).
- **Superseded:** the untracked draft
  `openspec/changes/add-case-pi-battery-and-feedback/` is removed. Its
  feedback requirements move here, rewritten for the new layout.
- **Unaffected:** the server, the phone client, the ESP32-CAM firmware and
  the Pi gun software. The trigger stays on GPIO13 (ESP32-CAM) and GPIO17
  (Pi), and the status LED on GPIO27 (Pi) and the board's own LED
  (ESP32-CAM).
- **New things to buy:**
  - M3 × 45 bolts and nylon-insert nuts;
  - a 1.5 A buck-boost module;
  - a right-angle micro-USB power plug and a 38 mm Pi Zero camera ribbon;
  - JST-XH leads and 1×6 Dupont housings;
  - a 6-pin socket and a tactile button;
  - optionally, a feedback device and its driver, and two buttons.
