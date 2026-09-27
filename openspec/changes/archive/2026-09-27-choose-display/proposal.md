## Why

The gun aims at one screen, but which screen was never the user's
choice: Windows and macOS used the primary monitor unless a raw
`BORESIGHT_CURSOR_RECT` rectangle was set, Linux left it to whatever
the compositor did with the cursor device, and the on-screen overlay
took a Qt screen index of its own. On a multi-monitor desk the cursor
and the markers can end up on different screens, with no way to pick
either from the phone.

## What Changes

- A display is chosen by its output name (`HDMI-A-1`, `\\.\DISPLAY2`,
  …) in `view.display`, from `--display`, or from a picker on the
  phone; empty means the primary display, as today. `GET /displays`
  lists what the machine has.
- The choice applies to the cursor and to the on-screen markers
  together, and can be changed while the server runs.
- Windows and macOS map the cursor onto the chosen monitor's rectangle.
  On Linux the cursor device is pinned to the chosen output through the
  compositor: KWin's input-device D-Bus interface on KDE Plasma, and
  `xinput map-to-output` on X11. Other Wayland compositors are reported
  as unable to pin it, with the fallback of their own tablet settings.
- **BREAKING**: `BORESIGHT_CURSOR_RECT` is removed in favour of the
  named display.
- The overlay accepts a display name as well as an index.

## Capabilities

### New Capabilities

### Modified Capabilities
- `cursor-injection`: the cursor maps onto a chosen, named display on
  every platform, replacing the Windows/macOS-only rectangle.
- `marker-overlay`: the overlay is placed on the same named display.
- `runtime-settings`: `view.display` joins the view preferences, with a
  flag, an endpoint to list displays and one to change it live.
- `phone-client`: the settings panel offers a display picker.

## Impact

- New `src/boresight/displays.py` (listing and Linux pinning); the
  Windows and macOS backends gain monitor listing and a settable
  target; the uinput backend pins its device; `marker_source.py`,
  `overlay/`, `settings.py`, `settings_routes.py`, `server.py`, the phone
  page and script, README.
- On KDE, pinning is saved by KWin in `kcminputrc` under the
  boresight-cursor device, like a choice made in System Settings.
