## Why

The first run on a real ESP32-CAM (12 fps, KDE Plasma 6.8 on Wayland,
libinput 1.32) showed two faults in the Linux cursor, both caused by the
uinput pen entering proximity once at startup and never leaving it:

- **The cursor blinked** in place while the aim held steady and every
  frame solved. libinput's tablet proximity-timer plugin forces any pen
  that has never sent a proximity out of its own out of proximity 50 ms
  after its last event, and back in with the next. Frames 80 ms apart
  meant one forced out/in pair per frame. The dropout hold could not
  help: its re-sends of an unchanged position are dropped by the kernel
  as duplicates, so they reach libinput as no event at all.
- **VS Code stopped taking the real mouse's clicks** after the aim left
  the screen, until its window was hidden and shown again. The pen was
  left hovering at the last aim, over VS Code (a native Wayland client),
  after a long stream of forced in/out pairs. Qt clients logged "Can't
  send tablet event with no proximity surface" from the same cycling.

## What Changes

- The Linux pen hovers only while something aims. It enters proximity
  with the first move, in the same event frame as that move's position,
  and leaves when the backend is told nothing is aiming.
- On its first entry the pen leaves and re-enters proximity once. A
  real proximity out is what makes libinput drop its forced-out timer
  for the device, so the cursor no longer blinks between frames.
- The cursor backend interface gains `idle()`: "nothing is aiming any
  more". The dropout hold calls it on each unsolved frame past its
  window (on every unsolved frame when holding is off). A session's
  cursor gate passes it on only while that session owns the cursor or
  no one does, and calls it when the owning session ends.
- The pen's tip goes down only while the pen hovers: a trigger pulled
  with nothing aiming clicks nowhere instead of at the last aim. While
  the tip is held, `idle()` leaves the pen in proximity, so a drag the
  trigger still holds is not ended under it.
- Windows, macOS and the Pi gun's HID mouse take `idle()` as a no-op:
  their cursor stays where it was put.

## Capabilities

### Modified Capabilities
- `aim-hold`: a lapsed hold tells the cursor that nothing is aiming,
  rather than sending nothing.
- `cursor-injection`: the Linux pen hovers only while something aims,
  makes one real proximity out on its first entry, and does not click
  while out of proximity.
- `cursor-ownership`: only the owning session, or any session while
  the cursor is free, can stop the aim, and the owner's disconnect does.

## Impact

- `inject.py` (`CursorBackend.idle`, the uinput pen's proximity and tip
  state, the smoothing wrappers, `FakeCursorBackend.idles`),
  `aim_hold.py`, `shooter.py`, plus no-op `idle()` in
  `inject_win32.py`, `inject_darwin.py` and `gun/hid.py`.
- README: the Linux pen in "Cursor injection", and "Holding through a
  brief dropout".
- No new dependencies, settings or wire changes.
