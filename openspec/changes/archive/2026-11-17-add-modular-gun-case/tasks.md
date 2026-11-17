# Tasks

## 1. Project scaffolding

- [x] 1.1 Create `hardware/case/` as a standalone uv project: `pyproject.toml` (package `boresight_case`, command `boresight-case`, build123d, manifold3d, pytest), `.python-version` 3.12, `uv.lock`, and `[tool.ruff] extend = "../../pyproject.toml"`; verify `uv sync --locked` and `uv run python -c "import build123d, manifold3d"` succeed inside `hardware/case/`
- [x] 1.2 Add `testpaths = ["tests"]` to the root `pyproject.toml` with a comment saying why, and git-ignore `hardware/case/dist/`; verify `uv run pytest -q` at the root collects the same number of tests as before and none from `hardware/case/`, and that root `uv run ruff check` and `ruff format --check` cover `hardware/case/`

## 2. Configuration and validity rules

- [x] 2.1 Implement the TOML configuration (`[build]`, `[style]`, `[printer]`) with defaults matching design.md, and the valid-configuration rules (Pi kit → USB tether only; `camera` only for the Pi kit); verify with tests that a Pi + AA configuration is refused before any geometry is built, with a message naming the board, the drawer and the reason, and that an ESP32-CAM + tether configuration is accepted
- [x] 2.2 Implement the style-parameter schema (name, type, default, range) and the range check; verify a test that an out-of-range parameter is refused and the message names the parameter and its range
- [x] 2.3 Add the `boresight-case` CLI skeleton (`build CONFIG --out DIR`, `build --all`, `coupon`, `check-skin`) that loads and validates the configuration and lists what it would build; verify `uv run boresight-case build --help` and a CLI test that an invalid file exits non-zero with the validation message

## 3. Purchased parts and interfaces

- [x] 3.1 Model every purchased part as an envelope in `vendor.py` (ESP32-CAM with OV2640 and header, Pi Zero 2 W, Camera Module 2 and 3, 2×2 AA and 2×2 AAA holders, 18650 cell ≤70 mm, TP4056 USB-C module, buck-boost module, slide switch, battery spring and plate contacts, MX switch, 20×10×6 lever microswitch, JST-XH 2-pin, Dupont 3-pin, 90° micro-USB plug, 470–1000 µF capacitor, 14×14×6 heatsink, M3 screws, nuts, heat-set inserts, spring), each with its dimensions and source (datasheet or caliper); verify a test that every envelope is a closed solid and that every entry has a source
- [x] 3.2 Implement `interfaces.py`: the module joint (tenon, socket, M3 × 12 into a nut trap or insert pocket, wire channel, teardrop hole), skin attachment point (hook slot plus M3 × 8), drawer bay key and contacts, bulkhead slot, switch-plate seat, each yielding its positive and negative feature from one definition and driven by the clearance and interference settings; verify tests that each pair mates with exactly the configured clearance and that raising the clearance by 0.1 mm opens every pair by 0.1 mm

## 4. Mesh checks

- [x] 4.1 Implement tessellation (0.05 mm) and the bed-fit, pairwise-interference (>1 mm³, declared press fits excepted) and envelope-fit checks on manifold3d meshes; verify unit tests on synthetic solids: an oversized box fails bed fit naming the part, two overlapping boxes fail, touching boxes pass, and a declared press fit passes
- [x] 4.2 Implement the overhang check (down-facing triangles more than 45° from vertical, off the bed, grouped into patches, with horizontal patches ≤10 mm across allowed as bridges and a small noise allowance); verify unit tests: a 60° overhang fails naming the part, a 45° chamfer passes, a 10 mm bridge passes, a 12 mm bridge fails, and a teardrop hole passes
- [x] 4.3 Implement the camera field-of-view frustum (per camera: FOV + 3° margin, from the lens to 60 mm past the muzzle) and the clearance-distance check used for the antenna rule; verify unit tests that a ring inside the frustum fails, a wider ring passes, and a nut 9 mm from a reference solid fails the 10 mm rule

## 5. Core modules

- [x] 5.1 Model the receiver (sockets for barrel, grip and rear cap, trigger well, board bay rails, wire channels, skin attachment points) and the barrel (tenon, bulkhead slot, muzzle aperture, light-guide window, ribbon and lead channel); verify tests that both pass bed fit and overhang, and that receiver + barrel assemble with no interference
- [x] 5.2 Model the grip (tenon, drawer bay, ceiling spring-contact seats; the regulator and power switch moved to the rear cap, see design.md) and the rear cap (tenon, LED seat, retains the sled); verify tests that the core assembly (receiver, barrel, grip, rear cap) passes bed fit, overhang and interference, and that each joint is secured by exactly one screw
- [x] 5.3 Start `hardware/case/README.md` with the module overview, the joint and the fastener options (nut traps or heat-set inserts); verify each module named in the README exists as a part in the build listing

## 6. Trigger cassette

- [x] 6.1 Model the cassette (one body on its top plate, a 1.75 mm filament pivot pin (an M3 axle would need a third screw length), spring pocket for OD ≤6 mm, free length 15–20 mm, over-travel stop screw into a nut trap, switch-plate seat, JST-XH plug seat) and the trigger lever; verify tests that the lever's swept volume from rest to the stop does not intersect any printed part, and that the cassette fits the receiver's well with one screw
- [x] 6.2 Model the MX plate (14.0 mm cut-out in a 1.5 mm web) and the microswitch plate (pegs at 9.5 mm, retaining lip), both on the same seat; verify per-plate geometric tests that at the default stop the switch is past its actuation point and short of its end of travel (MX: between 2 mm and 4 mm of stem travel), and that the lever at rest clears the actuation point
- [x] 6.3 Document trigger assembly, switch-plate swap and stop adjustment in the case README; verify the steps name only parts and screws present in the cassette's BOM entries

## 7. Board kits

- [x] 7.1 Model the ESP32-CAM bulkhead: edge rails, camera-module pocket that sets the aim, flash-LED cover, light-guide channel from the GPIO33 LED to the barrel window, capacitor pocket, and its screw at the end away from the antenna; verify tests: no interference with the board envelope, OV2640 frustum clear of all printed parts, no metal part within 10 mm of the antenna in every valid drawer configuration, and header pins reachable (a plug-on lead envelope on each used pin is free of printed material)
- [x] 7.2 Model the Pi camera bulkhead (pegs at 21 × 12.5 mm and snap clip, lens aperture sized per camera) for Camera Module 2 and 3; verify tests that both cameras fit the same pegs with no interference and that each camera's frustum is clear
- [x] 7.3 Model the Pi sled (upright against the left wall, pegs in two M2.5 holes plus clip, camera connector forward, heatsink space) with vent slots over the processor and the 90° micro-USB cable path down into the grip; verify tests: no interference with the Pi, heatsink, plug and cable envelopes; the micro-SD removal path is clear of every part except the rear cap; vents fall inside the vent keep-out
- [x] 7.4 Document both kits in the case README, with wiring tables for the default pins (ESP32-CAM GPIO13/GND and 5 V/GND with the capacitor; Pi pins 9/11/13 split to trigger and LED) and ESP32-CAM flashing with the bulkhead out; verify the pins match `firmware/boresight-cam` defaults and `deploy/pi/boresight-gun.example.toml`

## 8. Power drawers

- [x] 8.1 Model the drawer base (asymmetric key profile, two top contact plates, PETG cantilever latch with thumb tab) and the AA and AAA drawers holding 2×2 holders; verify tests: each drawer fits the bay with no interference when latched, a mirrored drawer collides with the bay before its plates reach the springs, and the latch clears every skin keep-out
- [x] 8.2 Model the 18650 drawer (cell pocket ≤70 mm, TP4056 module at the base with its USB-C port flush and an LED window) and the tether drawer (serpentine strain relief around three posts, routes for both the ESP32-CAM 5 V lead and the Pi cable); verify tests: no interference, the USB-C port and LED window lie inside their keep-outs, and the cable path is continuous from the Pi plug to the grip base for the Pi configuration
- [x] 8.3 Document the power path, battery swap, 18650 charging (switch off) and cell safety (protected cells, polarity) in the case README, including that the Pi kit is tether-only; verify the README's drawer list matches the valid-configuration table in code

## 9. Skins

- [x] 9.1 Build the keep-out zones as the union over every valid configuration (camera frustums, vents, trigger travel and finger path, drawer path and latch, power switch, USB-C port and indicator, cable exit, both LED windows) and the core's outer envelope; verify a test that every zone is non-empty and that the core's own parts stay out of the skin-only zones
- [x] 9.2 Model the `minimal` style (barrel, receiver and grip skins left and right, hook plus one screw each, flank-down print orientation) with its declared parameters; verify tests across every valid configuration: no keep-out intrusion, no interference, bed fit, overhang, each screw hole on its attachment point, and both ends of every parameter's range pass
- [x] 9.3 Model the `blaster` style (an original faceted design, finned shroud, separate accent parts on snap pegs) with its declared parameters; verify the same tests as 9.2 plus that the accent parts fit their pockets with the configured snap fit
- [x] 9.4 Verify by test that no skin part of either style contacts a functional part (board, camera, bulkhead, cells, cassette, wiring envelopes), so a skin swap cannot move the camera
- [x] 9.5 Write the skin design guide in the case README (attachment points, keep-outs, print orientation rules, the interface files and `check-skin`); verify the zones and attachment points named in the guide match the exported interface JSON

## 10. Build outputs

- [x] 10.1 Implement export per configuration: oriented STL and 3MF per part, STEP per part and of the assembly, and the skin interface (STEP with named keep-out solids and attachment markers, plus JSON); verify tests that the Pi + tether + MX + `minimal` build contains exactly the parts that configuration needs, that every mesh sits on z = 0, and that the interface JSON lists every attachment point and zone
- [x] 10.2 Implement the bill of materials (`bom.md`, `bom.csv`): printed parts with count, material (PETG for lever, latches and switch plates), perimeters and infill, then purchased parts with count and specification; verify tests that every purchased-part placement in the assembly appears with the right count, and that the screw total is ≤12 in at most two lengths for every valid configuration
- [x] 10.3 Implement the exploded-view SVG (hidden-line projection, parts moved along their insertion axes); verify a test that the SVG is produced for every valid configuration and names each part
- [x] 10.4 Implement `build --all` over every valid shipped configuration and the `coupon` part (joint, nut trap, peg, latch and MX cut-out at labelled clearances 0.15–0.35 mm); verify a test that `--all` produces one output directory per valid configuration, and that the coupon's volume estimates under 10 g of PLA
- [x] 10.5 Document the print guide in the case README (printer volume, clearance tuning with the coupon, materials, settings, downloading CI outputs); verify the documented commands run as written

## 11. Third-party skin check

- [x] 11.1 Implement `boresight-case check-skin CONFIG PART...` for STL and 3MF: core-envelope and keep-out intrusion, a clear hole on each covered attachment point, and bed fit, reporting each violation with the part and the zone or attachment point; verify tests that an exported `minimal` skin passes, the same skin with a plate over the Pi vents fails naming the part and the vent zone, and a skin with a filled screw hole fails naming the attachment point

## 12. Trigger mechanisms

- [x] 12.1 Add `mechanism` (`filament`, `bolt`, `button`; default `filament`) to the configuration, the catalogue and the configuration names, and name each mechanism's parts (`trigger-cassette-filament`, `trigger-lever-filament`, `trigger-cassette-bolt`, `trigger-lever-bolt`, `button-cassette`, `button-plunger`, `button-cap`); verify config and CLI tests that the 72 shipped configurations are listed with unique names and each configuration lists only its own mechanism's parts
- [x] 12.2 Model the bolt mechanism (an M3 x 12 through a 3.4 mm hub bore, its head counterbored into one boss and its nut pressed into the other, bosses grown to 5.5 mm radius); verify tests that both bolt parts print without support and fit the bed, the bolt clears the lever and the cassette and runs through its nut, the lever's sweep clears every printed part, and the stop meets the arm at both plates' default stops
- [x] 12.3 Model the button mechanism (a button cassette with the shared plate seat and a guide block under the front wall, a plunger whose head sits on the switch's rest contact and takes the spring, a cap pressed onto its front end; the stop screw in a lock nut in the guide block, its head the stop, set through a hole in the cap); verify tests that its parts print without support and fit the bed, the plunger's travel from rest to the stop clears every printed part, the default stop is past actuation and short of end of travel with both plates, and the cassette screw stays reachable from below
- [x] 12.4 Extend the trigger keep-out zone to every mechanism's travel and finger room; verify the skin tests pass across all 72 shipped configurations, and core parts stay out of every zone in a configuration of each mechanism
- [x] 12.5 Make `build --all` write a parts library (each distinct part once in `parts/` and `step/`, the interface once, and per configuration `bom.md`, `bom.csv` naming the part files, and `exploded.svg`), and count only teardown screws against the budget; verify tests that a part name always means the same geometry across configurations, every configuration's bill of materials names only files in the library, and teardown screws are at most 12 in two lengths in every configuration
- [x] 12.6 Document the three mechanisms and the `mechanism` key in the case README (assembling and swapping each, the bolt's counterbore and nut, the button's cap and stop) and add the new hand-checked scenarios to the checklist; verify the README tests cover every mechanism's purchased parts and the checklist covers every hand-checked scenario

## 13. CI

- [ ] 13.1 Add the `case` job to `.github/workflows/ci.yml` (setup-uv with Python 3.12 from `hardware/case/.python-version`, `uv sync --locked`, `uv run pytest -q`, `uv run boresight-case build --all --out dist`, and upload `dist/` as one artifact, `case`, only when the checks pass); verify a pull-request run is green and lists the artifact, and that a deliberately overlapping part on a scratch branch fails the job with no artifact published

## 14. Integration and first print

- [x] 14.1 Update `README.md` (hardware table and the ESP32-CAM section) and `deploy/pi/README.md` to point to the case as the recommended shell, keeping the Zapper as an alternative; verify the links resolve and the pins quoted match the case README
- [x] 14.2 Add the "What only a printed gun can confirm" checklist to the case README: the coupon's best clearance on the reference printer; every part slices with supports off; a full ESP32-CAM AA build and a Pi tether build both assemble and work; a full teardown and rebuild with only the hex key; 20 rebuild cycles without loose joints; battery swap without tools; 18650 charging and protection cut-off; regulator output 4.75–5.25 V at 1 A from 3.0 V; trigger actuation, stop and return with both plates; no vignetting in a captured frame; restyling keeps the zero; Pi temperature within 10 °C of open air after 30 minutes; ESP32-CAM Wi-Fi range in the case; verify every hand-checked scenario in the specs appears in the checklist
- [ ] 14.3 Print and build both kits, tick the checklist, and update `vendor.py` with caliper measurements and the defaults the first print revised; verify `uv run pytest -q` and `build --all` still pass after the revisions
