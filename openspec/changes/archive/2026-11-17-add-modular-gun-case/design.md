# Design

## Context

See proposal.md for motivation. Two guns exist in software today, and
neither has been built into a shell:

- **ESP32-CAM (AI-Thinker).** 27 × 40.5 mm, no mounting holes. The
  OV2640 sits on a short FPC and faces out of the board's face. Trigger
  on GPIO13 to GND (internal pull-up), spare button GPIO14, status LED
  GPIO33 (on-board, not on the header). Needs 5 V at ≥1 A with a
  470–1000 µF capacitor at the board. PCB antenna, u.FL optional.
  Flashed through its header (U0R/U0T/GPIO0) with a USB-serial adapter.
- **Pi Zero 2 W.** 65 × 30 mm, M2.5 holes on 58 × 23 mm. Camera
  connector on one short edge, micro-SD on the other, mini-HDMI and the
  two micro-USB ports on one long edge, GPIO header on the other.
  Trigger GPIO17 (pin 11), LED GPIO27 (pin 13), GND on pin 9: three
  adjacent pins on the odd row. Powered and enumerated through its USB
  data port, so it never runs from a battery. Runs OpenCV continuously,
  so it gets hot.
- Camera Module 2 and 3 share a 25 × 24 mm board and a 21 × 12.5 mm
  M2 hole pattern.

Repository constraints: Python 3.12 is the oldest supported and 3.14 is
developed on; ruff runs repo-wide in CI and the commit hook; the commit
hook runs `uv run pytest -q` from the root, which collects recursively
today because the root has no `testpaths`.

## Goals / Non-Goals

**Goals:**
- One parametric source for every part, with every mating feature
  derived from a single definition so the two sides cannot drift.
- Checks a computer can run for everything that can be checked without
  a printer: bed fit, overhangs, interference, keep-outs, screw budget,
  BOM completeness.
- A builder who never installs Python can print from CI outputs.

**Non-Goals:**
- Other boards (XIAO ESP32S3 Sense, Luckfox, a camera-less Pico) and the
  Camera Module 3 Wide. The bulkhead and sled interfaces leave room for
  them; this change draws none.
- A spare/aux button (GPIO14 has no action yet), recoil, IMU, rumble,
  sights.
- Battery gauge or low-battery warning (the ESP32-CAM has no free ADC1
  pin), and charging AA/AAA cells in the gun.
- Resin, SLS or injection-moulding tuning. FDM, 0.4 mm nozzle, PLA/PETG.
- Any change to firmware, server or Pi gun software, or their pins.
- Any shape that copies a commercial light gun, the Zapper included.

## Decisions

### Toolchain: a standalone build123d project in `hardware/case/`

Its own `pyproject.toml`, `uv.lock` and `.python-version` (3.12), with
build123d, manifold3d and pytest. It is not a uv workspace member, so
the root environment, its lockfile and the Pi's core-only install never
see OpenCascade. Package `boresight_case`, command `boresight-case`.
Its `[tool.ruff]` extends the root config, so the root lint and format
runs and hooks cover it unchanged.

*Why:* the user chose build123d: Python like the rest of the repo,
STEP export for remixers, and pytest for checks. *Alternatives:*
OpenSCAD (Customizer, but STL only and checks are awkward); hand-made
CAD (no checks, binary diffs). *Pinned Python:* OCP wheels lag new
CPython releases, so the case project pins 3.12 rather than following
the root's 3.14.

The root `pyproject.toml` gets `testpaths = ["tests"]` so the root
suite, and therefore the commit hook, never collects `hardware/case/tests`
(it would fail to import build123d).

### Layout

```
               ┌────────────┐ joint ┌───────────────┐ slot ┌─────────────────┐
  rear cap ────┤  receiver  ├───────┤    barrel     ├──────┤  cam bulkhead   │
  (switch,     │ Pi sled    │       │ wiring/ribbon │      │ ESP32-CAM | Pi  │
   regulator,  │ rails      │       └───────────────┘      └─────────────────┘
   Pi LED,     └──┬──────┬───┘
   Pi SD out)  joint│     │ rails + one screw
              ┌───┴──┐ ┌─┴───────────────┐
              │ grip │ │ trigger cassette├── switch plate: MX | microswitch
              │ contacts └─────────────────┘
              └───┬──┘
             bay  │
       ┌──────────┴──────────┐
       │    power drawer     │  AA | AAA | 18650 | USB tether
       └─────────────────────┘
```

A pistol: horizontal barrel, receiver behind it, grip angled down from
the receiver's rear, trigger cassette in a well under the receiver in
front of the grip.

- **ESP32-CAM** stands across the barrel on the bulkhead, camera
  forward, header pins pointing back into the barrel where plug-on leads
  fit. The receiver's board bay stays empty and takes wiring slack.
- **Pi Zero 2 W** stands upright on a sled against the receiver's left
  wall: camera connector forward (the ribbon runs straight down the
  barrel to the bulkhead), micro-SD to the rear (out with the rear cap
  off), GPIO header up, USB ports down. Mounted that way round, a real
  board's components face the gun's right, so the vent slots are in the
  right wall and the top, and skins keep a vent keep-out open. A 90°
  micro-USB plug turns the cable back over the grip socket's front rib,
  down the grip's bore, through a hole in the bay's ceiling and out of
  the tether drawer.

*Alternative:* Pi lying flat. Its USB ports would face a flank and the
cable would exit the side, and the SD card would need the sled out.

### One joint: tenon, socket, one screw into a trapped nut

Barrel, grip and rear cap each carry a rectangular tenon that enters a
socket in the receiver, with one M3 × 12 screw through the socket wall
into a hex nut trapped in the tenon. The tenon takes the bending, the
screw only stops withdrawal, and a channel through the tenon carries the
wires. Both halves print flat with no supports, and horizontal holes
are teardrops.

*Alternatives:* dovetail (prints well, but needs an end stop and its fit
depends on print direction); snap-fits (PLA fatigues over repeated
assembly); magnets (weak in shear, and pressed-in magnets fall out).

`fastener = "nut" | "insert"` switches every trap to a heat-set insert
pocket at the same position. It needs a soldering iron the first time
and nothing after.

### Every interface is defined once

`interfaces.py` holds each joint, attachment point, drawer key and
contact, bulkhead slot and switch-plate seat as one parametric object
that yields both the positive and the negative feature. Every part takes
its mating geometry from there. Purchased parts are envelope models in
`vendor.py` (board, camera, cells, holders, regulator, TP4056, switches,
connectors, screws, nuts, spring), each with its measured dimensions and
where they were measured, so a part from another vendor means one edit.

### Holding boards without screws

Boards and cameras sit on printed pegs (≥2.2 mm, PETG) through their
holes, with a snap clip over the edge. The ESP32-CAM has no holes, so
edge rails clamp it. Its camera module sits in a square pocket in the
bulkhead that sets the aim, since the camera, not the board, decides
where the gun points. The same clamp covers the white flash LED (GPIO4)
so it can never shine out or into the lens. The on-board red LED
(GPIO33) feeds a light guide, a length of clear 1.75 mm filament, to a
window on top of the barrel. The bulkhead's own screw sits at the end
away from the antenna, and no nut trap lies within 10 mm of it.

*Why no screws:* M2 and M2.5 would add two screw sizes and two tools
for parts that carry almost no load.

### Power: passive drawers, one regulator in the rear cap

```
  drawer ──[spring contacts]── switch ── buck-boost 5 V ── JST-XH ── board
  (cells)     grip ceiling     rear cap     rear cap
```

Each drawer is a printed cradle for an off-the-shelf holder: 2×2 AA,
2×2 AAA, or one 18650 (pocket long enough for protected button-top
cells, ≤70 mm). It has two flat contact plates on top that meet two
standard battery spring contacts in the grip's ceiling as it latches,
which makes the connection blind-mating. A rib down the bay's front wall
and a groove in the drawer are the key. A tongue in the base's front edge
hooks into a notch in the grip's front wall; it is pressed back from
below to release. Drawers print standing on their spine, so every member
rises straight from the bed.

The bay's ceiling is a 45-degree gable with a 10 mm flat that carries the
contacts: the grip prints standing on its base, and a full-width ceiling
would be a 32 mm bridge.

The pack voltage spans both sides of 5 V: alkaline 6.4 → 3.6 V, NiMH
5.6 → 4.0 V, Li-ion 4.2 → 3.0 V. So one buck-boost module serves every
drawer. It and the power switch, a snap-in rocker under the thumb, live in
the rear cap, inside its hollow tenon, clear of the Pi's micro-SD path.
*Why not in the grip:* the grip prints raked 18° to the receiver's flat
underside, so any compartment big enough for them ends in a ceiling that
overhangs; the rear cap prints flat and has the room. *Alternatives:* a
regulator per
drawer (three to buy, and more wiring in each drawer); no regulator (the
ESP32-CAM's AMS1117 drops out below about 4.4 V, so 18650 and tired
NiMH fail).

- **18650 drawer:** adds a USB-C TP4056 module with DW01 protection at
  its base, port flush, with a thin window over its LEDs. It charges with
  the switch off.
- **Tether drawer:** no cells. The cable runs through a serpentine
  channel around three posts, which relieves strain without a cable tie
  that would need cutting. For the ESP32-CAM, the cable's 5 V feeds the
  drawer contacts. For the Pi, the cable goes straight to the Pi and the
  contacts are unused.

### Trigger mechanisms

The trigger is a cassette under the receiver's floor, located by two
rails and held by one screw from below at its front, its switch lead
ending in a JST-XH 2-pin plug that comes up through the floor. Every
mechanism keeps that mount, so they swap without touching the receiver,
and every one shares the switch plates and the return spring's seat on
them. `mechanism` in `[build]` picks one; its parts are named for it.

The switch plates drop through a slot in the cassette's top plate into
grooves in its side walls. Each puts its switch's actuator on the same
line, 17 mm below the lever's pivot, so every mechanism meets them at the
same place:

- **MX plate:** a 14.0 mm square cut-out in a 1.5 mm web so the
  switch's clips catch. The stop is set at 3.0 mm, past actuation
  (2.0 mm) and short of bottom-out (4.0 mm).
- **Microswitch plate:** the switch passes through a window in the
  plate, on two teardrop-profiled pegs from a cheek through its 9.5 mm
  holes; the cassette's wall stops it sliding off. Mounted hinge up, its
  lever's tip takes the press. The stop is set at 2.0 mm, between its
  operating point (1.6) and its end of travel (2.4).

A compression spring (OD ≤ 6 mm, free length 15–20 mm; a ballpoint pen
spring usually fits), seated on a spigot on the plate, returns whichever
mechanism is fitted. Each mechanism's over-travel stop is an M3 × 12
screw in a captive nylon-insert lock nut, which holds it wherever it is
set, so the hex key is the only tool.

- **`filament`: a lever on a filament pin.** One body, printed upside
  down on its top plate, with the lever between two teardrop-profiled
  bosses on a 22 mm piece of 1.75 mm filament. The lever meets the switch
  only at a pad 17 mm below the pivot; its back face is recessed
  elsewhere so a microswitch's rising lever cannot touch it. Above the
  pivot, its upper arm swings forward onto the stop screw, in the front
  wall.
- **`bolt`: the same lever on an M3 bolt.** An M3 × 12 runs through the
  lever's 3.4 mm hub bore, its head in a counterbore deep in one boss and
  its nut pressed into the other, so a 12 mm screw spans the 22 mm
  cassette and no third screw length is needed. The bosses grow to
  5.5 mm radius to hold the counterbore and the nut pocket, both shaped
  to print sideways without support.
- **`button`: a push button.** No lever: a plunger slides straight back
  through a 9.5 mm guide block under the front wall. Its head presses the
  switch on the same line the lever's pad did, so the button moves as far
  as the switch does, and the return spring pushes on its lower half. The
  plunger sits 2.75 mm off centre so the cassette screw's way up from
  below stays clear. A cap, pressed onto the plunger's front end, is the
  finger pad. The stop screw sits in the guide block, in a lock nut that
  slides in through the right wall; its head stands proud of the block's
  front face and the cap's back meets it, and a hex key reaches it through
  a hole in the cap. *Why not a screw through the cap:* its head would
  stand out of the finger pad.

*Why the filament pin is the default:* nothing to buy. *Why a bolt as
well:* a filament pin wears; a steel axle does not.

The switch's leads end in the trigger plug at the cassette, so the
board-side lead never changes. The Pi's single 3-pin Dupont housing on
header pins 9/11/13 splits to the trigger and LED plugs.

### Skins

- **Attachment:** each skin part hooks a tab into a slot at one end and
  takes one M3 × 8 screw at the other, into a nut trap in the core. Six
  skin screws (left and right × barrel, receiver, grip) plus five core
  screws (three joints, cassette, bulkhead) make the 11 a teardown
  undoes, in two lengths. Screws that stay in the cassette (the stop
  screw, and the bolt mechanism's pivot) are M3 × 12 too, but are not
  undone in a teardown and do not count. A test enforces the budget. The grip's hooks
  go into its front wall, into a pocket in the key rib, since the drawer
  fills the bay behind its flanks.
- **Printability:** skins print outer flank down, so flanks are planar
  and edges are chamfered at ≤45°. Shape comes from the outline,
  chamfers and the accent parts. Accent parts press into holes through
  the skins on 3 mm pegs, a press fit set by the interference setting,
  with no glue.
- **Keep-outs:** the union of every valid configuration's zones, so one
  skin set fits both kits, every drawer and every trigger mechanism (the
  trigger zone holds each mechanism's travel and the finger's room in
  front of it). The camera's zone is a
  frustum from the lens, from its horizontal and vertical field of view
  plus a 3° margin, to 60 mm past the muzzle.
- **Styles:** `minimal` (flat panels, shortest print) and `blaster` (an
  original faceted design with a finned shroud and accents). Each style
  declares its parameters with type, default and range, and the build
  rejects out-of-range values before modelling.
- **Interface export:** a STEP file with the core envelope and each
  keep-out as a named solid, attachment points as named marker
  cylinders, and the same data as JSON (position, axis, screw, hook
  slot).

### Checks run on meshes, with manifold3d

Every part is tessellated (0.05 mm) and checked as a mesh:

- **Interference:** pairwise intersection volume over 1 mm³ fails,
  except declared press fits. The threshold absorbs coincident-face
  noise.
- **Purchased parts:** envelopes must not overlap printed parts.
- **Field of view:** the frustum must not overlap any printed part.
- **Bed fit:** checked in print orientation.
- **Overhangs:** down-facing triangles more than 45° from vertical,
  off the bed, are grouped into connected patches. A horizontal patch
  whose minimum bounding rectangle is ≤ 10 mm across is a bridge.
  Anything else, beyond a few mm² of tessellation noise, fails.

The core envelope a skin may not enter is the core's outside filled in,
less the room each skin hook takes through its wall, so a remixed skin
cannot hide inside the receiver.

There are also tests for the screw budget, BOM completeness (every
placed purchased part appears with its count), 10 mm antenna clearance,
refusal of invalid configurations and parameter ranges.

*Why meshes and not OpenCascade booleans:* manifold booleans are fast
and robust across ~20 assemblies, and the same code checks a
third-party STL skin, which a B-rep check cannot load reliably.

### Configuration and command

A TOML file, like the repo's other settings:

```toml
[build]
board = "esp32-cam"        # or "pi-zero-2w"
power = "aa"               # "aaa", "18650", "usb"
trigger = "mx"             # or "microswitch"
mechanism = "filament"     # "bolt" or "button"
style = "blaster"          # or "minimal"
camera = "cm3"             # Pi kit only: "cm2" or "cm3"

[style]                    # style parameters, each range-checked
shroud_length = 20

[printer]
volume = [180, 180, 180]
clearance = 0.25
interference = 0.05
fastener = "nut"           # or "insert"
```

- `boresight-case build CONFIG --out DIR` builds one configuration.
- `boresight-case build --all --out DIR` builds every valid shipped
  configuration, and `build --shipped NAME` one of them by name
  (`boresight-case list` names them).
- `boresight-case coupon` builds the fit coupon.
- `boresight-case check-skin CONFIG PART...` checks skins supplied as
  STL or 3MF.

Outputs per configuration:

- `parts/*.stl|3mf`, oriented on the bed
- `step/` (each part and the assembly)
- `interface/`
- `bom.md` and `bom.csv` (the print list with material, perimeters and
  infill, then purchased parts)
- `exploded.svg`, a hidden-line projection with each part moved out
  along its insertion axis

`build --all` writes a parts library instead, since 72 configurations
share most of their parts: `parts/` and `step/` hold every distinct
part once (a part's name always means the same geometry, which a test
checks), `interface/` is written once, and `configurations/<name>/`
holds each configuration's `bom.md`, `bom.csv` (naming the part files to
print) and `exploded.svg`. It leaves out the per-configuration assembly
STEP, which `build CONFIG` still writes.

The `dist/` output directory is git-ignored.

### CI

One `case` job in `hardware/case` (setup-uv picks Python 3.12 from its
`.python-version`): `uv sync --locked`, `uv run pytest -q`, then
`boresight-case build --all --out dist`, and `dist/` uploaded as one
artifact, `case`. The upload runs only if the checks pass, so a change
that breaks one publishes nothing. *Alternative:* one artifact per
configuration, which was the plan with 24 configurations; at 72 it is
about 800 MB per run, nearly all of it the same parts repeated.

The existing Python jobs keep running ruff over the whole tree,
`hardware/case` included.

## Risks / Trade-offs

- [72 configurations slow the checks] → Parts are built once per module
  and cached, and the tests tessellate each part object once, so a
  configuration costs only its interference checks.

- [Purchased parts vary by vendor (holders, TP4056, ESP32-CAM clones,
  regulators)] → Every part is one envelope in `vendor.py` with its
  measured source. Pockets have clearance plus crush ribs. The BOM names
  what was measured.
- [Never yet printed: every dimension is a guess until a first print] →
  `hardware/case/README.md` carries a checklist of what only a printed
  gun confirms, as `deploy/pi/README.md` does. The shipped defaults are
  revised from it.
- [The overhang heuristic can miss or over-report] → Slice every part
  with supports off on the first print and record the result. Tune the
  bridge and noise thresholds from that.
- [Buck-boost current at the lowest input (3.0 V for 1 A out is about
  1.9 A in)] → Bench-test the chosen module at 3.0 V. Fall back to a
  higher-current module of the same footprint class.
- [NiMH in series can be driven into cell reversal] → Choose a regulator
  with under-voltage lockout around 3.0 V, set by its enable input if it
  has no lockout of its own. 3.0 V is also above the 18650 protection
  cut-off.
- [The Pi throttles in a closed case] → Vents over the processor and a
  heatsink. The 10 °C rule is measured on the first build.
- [The ESP32-CAM's Wi-Fi range drops in the case] → Plastic only near
  the antenna, and 10 mm clear of metal. The u.FL route stays available.
  Range is checked by hand.
- [OCP wheels are large and lag Python releases] → A separate project
  pinned to 3.12, with the uv cache in CI.
- [`testpaths = ["tests"]` would hide a test placed outside `tests/`] →
  None exists today. The change is noted in the root pyproject.
- [PLA creeps when warm (cars, sun)] → PETG for structural and moving
  parts, in the print list.

## Migration Plan

Additive. The README and `deploy/pi/README.md` hardware tables gain the
case as the recommended shell and keep the Zapper as an alternative.
Rollback is removing `hardware/case/`, the CI job and the `testpaths`
line.

## Open Questions

- Which buck-boost module goes in the BOM (e.g. a Pololu S9V11F5-class
  part or a TPS63020 board). It is chosen at the bench test; the pocket
  is an envelope either way.
- Whether to also attach the CI outputs to GitHub releases, since
  workflow artifacts expire.
- The camera ribbon length for the Pi kit. It is set once the barrel
  length is fixed, and the BOM states it.
