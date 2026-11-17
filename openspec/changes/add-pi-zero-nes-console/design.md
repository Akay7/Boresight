# Design

## Context

`boresight-gun` (from `add-pi-zero-usb-gun`, now archived) is built
from these parts:

- **Capture.** A capture thread fills a one-frame slot, so stale frames
  are dropped rather than queued.
- **Aiming.** The aim loop runs `AimPipeline` + `HoldingPipeline` and
  calls a cursor backend: `move_absolute(x, y)` with 0..1 coordinates,
  `press` and `release`. Today the only backend is `HidGadgetBackend`.
- **Trigger and LED.** The trigger is debounced in its own thread. An
  LED shows the state.
- **Configuration and tests.** Configuration is one TOML file.
  `--emulate` swaps the camera, pins and HID for fakes.

On-screen tags already come from one pure function,
`boresight.overlay.layout`. Both the overlay renderer and the solver call
it with the display's pixel size, so the drawn and solved positions
cannot differ (`marker-overlay` spec). Its placement puts tags at the
four corners and the four edge midpoints of the full screen. The
pipeline already solves with a subset of the markers visible
(`add-partial-marker-visibility`).

The Pi Zero 2 W has:
- four Cortex-A53 cores at 1 GHz
- 512 MB of RAM, shared with the GPU and the camera ISP
- a VideoCore IV GPU, driven by Mesa `vc4` through KMS
- a mini-HDMI port
- one micro-USB OTG port and one power-only port

Motivation is in proposal.md. Required behaviour is in
`specs/gun-console/spec.md`.

## Goals / Non-Goals

**Goals:**
- One Pi, one program: emulator, markers and tracking.
- The game's frame pacing never depends on tracking load.
- Tags and solver layout come from one function, as on the desktop.
- Everything except the GPU, HDMI, camera and GPIO is testable on a PC
  with no ROM.

**Non-Goals:**
- Systems other than the NES. The frontend is generic libretro, but only
  a NES core is installed, configured and tested.
- Save states, an on-screen menu, shaders or CRT filters, rewind,
  netplay, cheats.
- More than one gun, and Zapper on both ports.
- Composite video, audio on a 3.5 mm jack, Wi-Fi play.
- Compensating Zapper latency beyond using the latest aim each game
  frame.
- Generating lens or zero calibration on the Pi. As in USB mode, these
  are files copied from the server.

## Decisions

### Our own small libretro frontend, not RetroArch

The gun loads a libretro core (`.so`) through `ctypes`. It runs
`retro_run` once per display refresh and draws the frame with SDL2. It
answers the core's input callbacks itself:
- the Zapper position and trigger from the aim
- Start and Select from the GPIO buttons or a gamepad

This keeps three things in one place:
1. The tags are drawn by the same code that computes the solver's
   layout. A RetroArch overlay would be a PNG plus a config file, which
   is a second copy of the layout.
2. The aim goes straight to the Zapper as NES pixels. With RetroArch it
   would go through a uinput mouse, and RetroArch's own viewport maths
   would have to agree with ours.
3. One process tree is supervised by one systemd unit.

*Alternative:* RetroArch with an overlay image and a uinput absolute
mouse. It is mature and has shaders and a menu. But it puts the layout
in two places and adds a second program to configure and keep running
at boot. The frontend we need is small: video, audio, input, core
options and pacing.

### Nestopia UE from apt as the NES core

`libretro-nestopia` is packaged in Debian Trixie for arm64. It is
accurate and supports the Zapper through the libretro lightgun device on
port 2. *Alternative:* FCEUmm, which is lighter on the CPU but not
packaged, so we would have to build it on the Pi. The core path is a
config value, so FCEUmm can be dropped in if Nestopia turns out too
heavy. Task 2.1 checks the core's Zapper option and lightgun coordinate
convention first, before anything depends on them.

### Two processes: the game process and the tracker process

The **game process** runs the emulator, rendering, audio and all buttons.
The **tracker process** is a child started with `multiprocessing`. It
runs the existing capture and aim loop with a new backend. Instead of
writing HID reports, that backend writes the latest aim to a small
shared-memory record: x, y, solved, and the time.

Two processes rather than threads, for two reasons:
- **The GIL.** The emulator calls back into Python for every video frame
  and audio batch. The pipeline runs Python between its OpenCV calls. In
  one process each would delay the other, and game pacing would wobble
  with tracking load.
- **Priority control.** Separate processes can be given separate
  priorities. The game process is pinned to core 0 at higher priority.
  The tracker gets cores 1–3 and drops camera frames when it is short,
  as it already does.

The parent computes the layout from the output size before it starts
the child, and hands the child the resulting `MarkerMap`. That is still
"one computation": nothing is written to disk or transcribed.

The trigger, Start and Select are read in the game process. Each game
frame samples them along with the latest aim, so a pull and the aim used
for it come from the same moment.

### Display: SDL2 on KMS/DRM, 1280×720 by default

The gun uses SDL2 through `python3-sdl2`, with the KMSDRM video driver
and the GLES2 renderer on `vc4`. It needs no X or Wayland. The `console`
installer sets the boot target to `multi-user.target`, so a desktop
image does not hold the display. The output mode defaults to 1280×720
and can be changed in `[console] resolution`.

720p because the GPU, the camera ISP and the CPU share one LPDDR2 bus.
Scaling a 256×240 texture to 1080p buys nothing visible at TV distance
and costs memory bandwidth that tracking uses.

Each frame draws two textured quads with vsync on:
- the NES frame, scaled with nearest-neighbour into the game viewport
- a static bars texture, rendered once at startup from the layout

The refresh rate matches the game's region when the TV offers it: 60 Hz
for NTSC, 50 Hz for PAL. Otherwise it stays at 60 Hz.

### Pacing and audio: the display clock leads

Each vsync runs exactly one `retro_run`. The NES's 60.0988 Hz therefore
runs 0.16 % slow on a 60 Hz output, which nobody can see. Audio goes into
an SDL audio queue. To keep the queue at about 3 frames of sound, it is
resampled by up to ±0.5 % according to how full the queue is. This is
dynamic rate control, which keeps sound smooth with no drift and no
crackle.

*Alternative:* pace from the audio clock. That gives torn or duplicated
frames, which are worse for a shooting game than a 0.16 % speed change.

### Layout: tags only in the side bars

The tags go in the side bars through a new pure function next to
`overlay_layout`, called `bar_layout(output_px, viewport, margin_px)`.
It places six tags:
- markers 0–3 at the corners of the bars
- markers 7 and 5 at the middle of the left and right bars

There are no top or bottom middle tags (4 and 6), because those spots
are inside the game picture. Each tag's size is the largest that fits
the bar width with its quiet-zone patch and the margin. At 720p with the
8:7 NES pixel aspect:
- the game is ≈878 px wide
- each bar is ≈201 px
- each tag is ≈120 px, about 9 % of the screen width

That is twice the desktop overlay's default, which helps detection at
living-room distance. Below a minimum tag size, set from the same
"≈20 px in frame" rule as `DEFAULT_TAG_FRACTION`, the function raises,
and the gun refuses to start with the resolution named.

The viewport is computed by one function, from the output size and the
pixel aspect. The renderer, `bar_layout` and the Zapper mapping all use
it, so the picture, the tags and the hit maths agree.

Because the tags are static, the TV's processing lag does not affect
the aim. The camera sees fixed tags, not game content.

### Zapper mapping

The pipeline's aim (x, y) is normalized over the full output, because
the layout is in output pixels with a scale of 1.0. The mapping is:

1. Convert the aim to output pixels.
2. Subtract the viewport origin.
3. Divide by the viewport size.
4. Convert the result to the core's lightgun range: −0x7fff..0x7fff over
   the content.

The aim counts as off-screen, and the libretro off-screen flag is set,
when any of these hold:
- it lies outside the viewport
- there is no aim yet
- the aim-hold time has run out (from the shared `solved` time)

The core does the Zapper's light test against its own framebuffer. The
Zapper therefore works with LCD TVs and their input lag, which a real
Zapper does not.

### Inputs

- **Start and Select.** `[pins] start` and `select` are optional BCM
  pins, debounced like the trigger and validated with all the other
  pins.
- **Gamepad.** SDL GameController. It needs the OTG port in host mode,
  so `install.sh --mode console` writes `dtoverlay=dwc2,dr_mode=host`.
  `--mode usb` (the default) keeps `dr_mode=peripheral`.
- **Mode mismatch.** If `mode` and the overlay do not match, for example
  console mode with peripheral USB, the gun logs a warning that names
  the installer command. Everything except the gamepad still works.
- **The gadget service.** It is enabled only in USB mode.

### ROMs and persistence

`[console] rom` is a file or a folder. With a folder, the index of the
current ROM is kept in `/var/lib/boresight/console.json`, the systemd
`StateDirectory`. Holding Select for 1 s at startup advances it.

With no ROM, or a ROM that fails to load, the program draws the bars
with tags plus a centred text message. It keeps tracking and logging the
aim, so aiming can be set up before any game is added.

### Power and heat

Every 5 s the gun reads the firmware throttle flags, from
`/sys/devices/platform/soc/soc:firmware/get_throttled` or else
`vcgencmd get_throttled`. These bits matter:
- 0x1: under-voltage now
- 0x4: throttled now
- 0x8: soft temperature limit
- the sticky bits for each of these

Each newly seen condition is logged once. While under-voltage is present
the LED shows the error pattern.

### Testing without a Pi

The game process is written against three seams.

**Core.** Implemented by the ctypes libretro wrapper and by a pure-Python
stand-in. The stand-in draws a known frame and records every lightgun
and joypad poll. There is also a 60-line C stub core, built by the test
when a C compiler is present, which exercises the real ctypes binding
with no ROM. CI has `cc`.

**Display.** The SDL renderer can run with `SDL_VIDEODRIVER=offscreen`
and the software renderer, so a composed frame can be read back. The
test runs the existing detector on that frame. This checks two things:
- every tag is found at its `bar_layout` position
- none are found inside the viewport

**Tracker.** The emulated tracker is the existing `--emulate` frame
source and `AimPipeline`, writing to the shared record.

## Budget

These are estimates to check against measurements in task 8.1.

| Load | Where | Estimate |
| --- | --- | --- |
| Nestopia, NTSC 60 fps | core 0 | well under one core. FCEUmm is the fallback if not |
| Render 2 quads, 720p | GPU | negligible |
| Audio resample, ~800 samples/frame | core 0 | < 1 % |
| Capture 640×480 YUV, take luma | ISP + DMA | negligible CPU |
| Detection + solve at 640×480 | cores 1–3 | not yet measured on a Pi (task 7.2). Target ≥ 30 fps |
| RAM | | OS (Lite) ~100 MB, tracker with OpenCV ~120 MB, game ~60 MB, GPU/CMA 128 MB. Fits 512 MB |

**Power.** At 5 V the Pi draws about 0.6–1.0 A with all cores loaded and
the camera on. A TV's USB port often gives 0.5 A. That is why the
proposal asks for a 2.5 A supply and why under-voltage is reported.

**Heat.** With all cores busy the Pi reaches its soft limit without a
heatsink. With one it should not.

## Risks / Trade-offs

- **The TV overscans and crops the corner tags.**
  → `[console] margin_px`, as with the desktop overlay's margin. The
  README says to set the TV to "Just scan" / "Screen fit".
- **Game pacing stutters when tracking peaks.**
  → Separate processes, core pinning and priority. The frame-time
  histogram is logged so this shows up in measurements.
- **Nestopia is too slow, or its Zapper convention differs.**
  → It is checked first (task 2.1), and the core is configurable, with
  FCEUmm as the fallback.
- **SDL KMSDRM / GLES quirks on `vc4`.**
  → A software-render fallback through SDL's KMSDRM dumb buffers. It is
  slower but enough for 720p with two blits. Choosing it is a config
  flag.
- **An HDMI cable and a power cable now hang off the gun.**
  → The README recommends a right-angle mini-HDMI plug and a thin, long
  cable. Putting the Pi in a box by the TV with a long CSI cable is out
  of scope.
- **None of the Pi side has run on hardware yet.** The USB gun's
  hardware tasks are also open.
  → Hardware tasks are separated and come with measurement steps.
  Console mode must not ship as tested until they are done.
- **Copyright.**
  → No ROMs in the repository, tests or packages. The tests use the
  stand-in and stub cores only. The core is a separate GPL package,
  loaded at runtime from apt.

## Migration Plan

Nothing migrates, because `mode` defaults to `usb`. To switch an
installed gun:
1. Set `mode = "console"`.
2. Run `sudo deploy/pi/install.sh --mode console`. It installs the NES
   core and SDL2, switches the OTG port to host and sets the boot
   target.
3. Reboot.

To go back, run `--mode usb` and reboot.

## Open Questions

- Should the NES's top and bottom 8 overscan lines be cropped by
  default? It is a viewport parameter only, and every consumer already
  uses the one viewport function.
- Is 720p the right default once it is measured, or should it follow
  the TV's preferred mode up to 1080p?
