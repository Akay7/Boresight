# Proposal

## Why

Both self-contained guns, the ESP32-CAM and the Raspberry Pi Zero 2 W,
assume a donor shell: the README says to gut an NES Zapper. Few people
own one, it fits neither board well, and it gives no place for a
battery, a camera mount that holds its aim, or a better trigger switch.
A printable case of our own, built from modules, lets anyone build
either gun from a spool of filament and common parts, rebuild it with a
different board, battery or switch, and restyle it without touching the
electronics.

## What Changes

- Add a parametric, FDM-printable gun case, generated from code in a new
  standalone project under `hardware/case/` (build123d, Python).
- **Modular core.** The structure is a set of modules joined by one
  common joint type: receiver (the hub), barrel, grip, rear cap, a
  drop-in trigger cassette, a camera bulkhead at the muzzle, a board sled
  and a power drawer in the grip. The core alone is a working gun.
- **Board kits.** The same core takes either board: an ESP32-CAM kit
  (the whole board mounts on the muzzle bulkhead, camera forward) or a
  Pi Zero 2 W kit (Camera Module 2 or 3 on the bulkhead, the Pi on a
  sled in the receiver, a ribbon between them). Switching boards swaps
  only the kit and the power drawer.
- **Power drawers.** Four interchangeable drawers slide into the grip:
  4×AA, 4×AAA, one 18650 (with USB-C charging through the grip base) and
  a USB tether. All battery drawers feed one buck-boost regulator, in the
  rear cap with the power switch, that gives the board 5 V. The Pi kit
  always uses the tether, since its USB cable is both power and data.
  Batteries swap without tools.
- **Trigger mechanisms and switches.** The trigger is a drop-in cassette
  on one mount (rails, one screw, the trigger plug), in three mechanisms:
  a lever on a 1.75 mm filament pin, a lever on an M3 bolt, or a push
  button whose printed cap presses the switch straight on. Each takes
  either an MX-style mechanical keyboard switch or a lever microswitch on
  the same swappable switch plates, with an adjustable over-travel stop
  and a return spring.
- **Take-apart design.** Modules join with M3 screws into nut traps or
  tool-free latches, and every electrical connection that crosses a
  module boundary is a plug. No glue, no soldering and no cutting to
  take it apart.
- **Swappable looks.** The appearance is a separate set of skin parts
  that attach to the core at published attachment points and stay out
  of published keep-out zones (camera view, vents, trigger travel,
  drawer path). Two original skin styles ship. Third-party skins,
  including STL ones, can be checked against the same rules.
- **Printability.** Every part fits a 180×180×180 mm bed, prints without
  supports in its exported orientation, and has fit clearances tuned
  through one setting that a printable fit-test coupon helps calibrate.
- **Build and checks.** One command generates the oriented STL and 3MF
  for each part, STEP for remixing, and a bill of materials and an
  exploded view for a configuration; for every configuration at once, it
  writes each distinct part once, with a bill of materials and drawing
  per configuration. Automated checks for bed fit, interference,
  keep-outs and overhangs run in CI, which publishes that parts library
  as one artifact.
- The README's hardware tables point to the case instead of a Zapper
  shell. No firmware or server behavior changes. The existing trigger
  and LED pins are used as they are.

## Capabilities

### New Capabilities
- `case-modules`: the case's mechanical and electrical architecture:
  the core modules and their joints, the board kits, the power drawers,
  the trigger mechanisms and their switch plates, which configurations
  are valid, and how the gun comes apart and goes back together.
- `case-skins`: the appearance layer: skins separate from structure,
  the skin interface (attachment points and keep-out zones), the shipped
  styles, and checking a third-party skin.
- `case-fabrication`: making the parts: print constraints, tolerances
  and the fit coupon, the generator's outputs (meshes, STEP, BOM,
  exploded view), and the automated geometry checks.

### Modified Capabilities
- `code-quality-gate`: CI also builds the case and runs its checks. The
  commit hook's test run stays the package's suite and does not include
  the case checks, which need the heavy CAD kernel.

## Impact

- New: `hardware/case/` (its own `pyproject.toml`, `uv.lock` and Python
  pin, the generator package, skins, tests and an assembly README).
- Changed: `.github/workflows/ci.yml` (a case job that checks and builds
  every shipped configuration and uploads one parts library), the root
  `pyproject.toml` (pytest limited to `tests/` so it never collects the
  case's tests), and `README.md` plus `deploy/pi/README.md` hardware
  sections.
- Dependencies: build123d (OpenCascade via OCP) and manifold3d, in the
  case project only. The `boresight` package and its environment are
  unchanged.
- Hardware a builder buys: M3 screws and nuts, a pen spring, JST-XH
  plugs, a buck-boost 5 V module, a snap-in rocker switch, battery holders or a
  TP4056 module, and the switch of their choice. No custom PCB.
- Unaffected: the server, the phone path, the ESP32-CAM firmware and the
  Pi gun software.
