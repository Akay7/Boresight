## Context

The cursor's target screen is decided differently per platform today:
`inject_win32` and `inject_darwin` map onto the primary monitor or a
`BORESIGHT_CURSOR_RECT`; the uinput device is mapped by the compositor.
On KDE Plasma (Wayland) KWin exposes every input device on D-Bus
(`/org/kde/KWin/InputDevice/<sysName>`); the boresight-cursor device
appears as a tablet tool with a writable `outputName`. Probing on this
machine showed that setting it works and that KWin persists it in
`~/.config/kcminputrc` keyed by vendor, product and device name. The
overlay picks a Qt screen by index.

## Goals / Non-Goals

**Goals:** one named display for cursor and markers, chosen in the file,
by flag or from the phone, live; honest failure where it cannot apply.

**Non-Goals:** GNOME/sway/other Wayland pinning (reported, not done);
spanning several monitors; per-player displays.

## Decisions

- **Names, not indices.** Output names are what the compositor, xrandr,
  Qt (`QScreen.name()`) and Windows (`\\.\DISPLAYn`) share; an index
  can change when a monitor is unplugged. macOS has no output names, so
  its displays are named by their CoreGraphics display ID.
- **Listing per platform** (`displays.py`): Windows
  `EnumDisplayMonitors`/`GetMonitorInfoW`; macOS
  `CGGetActiveDisplayList`/`CGDisplayBounds`; Linux `kscreen-doctor -j`
  on KDE, else `xrandr --listmonitors`. Each behind an injectable
  runner so tests use canned output.
- **Linux pinning by the compositor, not by maths.** Mapping to a
  sub-rectangle of the device range would depend on how each compositor
  maps an absolute device, which we cannot observe. Pinning through
  KWin or `xinput map-to-output` is exact. `busctl --user` and `xinput`
  are called as subprocesses: no new Python dependency. KWin sees the
  device a moment after it is created, so pinning polls briefly.
- **Backends own the mapping.** Each backend gets `show_on(display)`;
  the server applies the setting once at startup and on `POST /display`.
  A fake backend records it.
- **The primary display is the empty name.** Saved as `""`, so a file
  written on one machine does not name a monitor another lacks.

## Risks / Trade-offs

- KWin writes the pin into `kcminputrc` → the same place System
  Settings would; documented in the README.
- Pinning cannot be verified in CI → canned subprocess output in tests;
  real multi-monitor checks left as hardware tasks.
- `kscreen-doctor` output format may change → parse defensively and fall
  back to xrandr.
