## Why

Printed markers carry three costs the project has been paying in full:
they must be printed at verified physical size, they must be measured
into a `markers.toml` by hand, and they sit on paper beside a bright
panel — which README calls the dominant failure mode, because
auto-exposure chases the screen and the tags underexpose to mud.

Drawing the tags on the screen instead removes all three at once. They
become emissive, so the dynamic-range problem disappears. Their
positions are known exactly in screen pixels, so the marker-map
calibration milestone disappears with them. And there is nothing to
print, cut, or stick to a television.

It also relieves the minimum working distance. Bezel markers sit
outside the panel, so at close range every one of them falls outside the
camera frustum — measured at zero detected markers below 1400mm on the
reference scene. On-screen tags sit *inside* the panel, so a close-range
camera keeps seeing them.

The catch, and the thing this change is really about: an overlay that
accepts mouse or keyboard input is worse than useless here. Boresight
injects its clicks at the aim point, which is by definition on the
screen the overlay covers. An overlay that took input would swallow
every shot the gun fired — the system would be shooting its own
overlay. Input transparency is not a nicety; nothing works without it.

## What Changes

- Add an on-screen marker overlay: ArUco tags drawn over whatever is
  already on the display, always on top, and **transparent to mouse and
  keyboard** so every event reaches the application beneath.
- Support X11, Windows, and Wayland, through one Qt code path plus a
  Wayland-specific layer-shell addition. Where a platform genuinely
  cannot host such an overlay — GNOME's Wayland compositor being the
  significant case — say so at startup and name printed markers as the
  alternative, rather than showing a window that quietly eats clicks.
- Derive the layout from the same pure function the overlay draws from,
  so the solver and the renderer cannot disagree about where a tag is.
  No file is written and no message is passed; both sides compute the
  same layout from the same screen geometry.
- Add the overlay as an **optional dependency group**. The core server,
  pipeline and solver stay headless — the project uses
  `opencv-python-headless` deliberately — and a GUI toolkit only
  arrives if you ask for the overlay.
- Add a marker layout source selectable by configuration, so printed
  and on-screen markers are alternatives rather than a replacement. A
  printed layout still works exactly as it does today.
- Keep the tags legible against arbitrary screen content by drawing a
  solid quiet-zone patch behind each one, rather than compositing them
  onto whatever pixels happen to be underneath.

Explicitly out of scope: drawing the tags inside a game's own render
loop (an injected shader or emulator patch), macOS support, and any
change to `solve.py`, `detect.py` or `pipeline.py` — the overlay
produces a layout in the format they already consume.

## Capabilities

### New Capabilities
- `marker-overlay`: tags rendered onto the live display — placement and
  layout derivation, always-on-top behaviour, transparency to mouse and
  keyboard input, per-platform support and the diagnostics for where it
  is unavailable, and the overlay's lifecycle.

### Modified Capabilities
<!-- None. The overlay produces a marker layout in the shape
     `marker-map` already defines and `aim-pipeline` already consumes;
     neither capability's requirements change. -->

## Impact

- New: `src/boresight/overlay/` (the layout function and the platform
  backends), a launcher entry point, and their tests.
- Modified: `pyproject.toml` gains an optional `overlay` dependency
  group. Configuration gains a way to select an on-screen layout
  instead of a file.
- Unchanged: `solve.py`, `detect.py`, `pipeline.py`, `marker_map.py`,
  `stream.py`, `server.py`. This change is a new *producer* of marker
  layouts, not a change to anything that consumes one.
- Dependencies: Qt (PySide6) — but only in the optional group, so a
  default install is unaffected. Wayland additionally needs a
  layer-shell integration, which is the reason Wayland support is
  conditional rather than universal.
- **Known limitation, applies to every platform:** an overlay cannot
  draw above a fullscreen-*exclusive* application. Emulators must run
  borderless-windowed. This is the same constraint README already
  records for synthetic input, and it needs stating in the same breath
  as the feature.
- README: "Future work" describes on-screen markers as unbuilt; the
  Hardware, Marker system, and Milestones sections all assume paper.
