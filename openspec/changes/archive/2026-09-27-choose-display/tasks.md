## 1. Displays

- [x] 1.1 `displays.py`: `Display`, `list_displays()` for Linux (kscreen-doctor JSON, xrandr), with an injectable runner
- [x] 1.2 Windows monitor listing (`EnumDisplayMonitors`) and macOS display listing on their API objects
- [x] 1.3 Linux pinning: KWin D-Bus via `busctl --user`, X11 `xinput map-to-output`, clear error elsewhere

## 2. Backends and overlay

- [x] 2.1 `show_on(display)` on the uinput, Windows, macOS and fake backends; remove `BORESIGHT_CURSOR_RECT`
- [x] 2.2 Overlay `--display` accepts a name; the controller starts the overlay on the chosen display and restarts it on change

## 3. Settings, API, phone

- [x] 3.1 `view.display` and `--display`; applied at startup, failing with the reason
- [x] 3.2 `GET /displays`, `POST /display`; saved with the view preferences
- [x] 3.3 Phone: display picker in the settings panel

## 4. Tests and docs

- [x] 4.1 Tests: listing parsers, pinning commands, Windows/macOS rectangles, unknown display refused, overlay command, routes, save
- [x] 4.2 README: replace `BORESIGHT_CURSOR_RECT` with choosing a display
- [ ] 4.3 Hardware: choose a second monitor on KDE Wayland, X11, Windows and macOS and check cursor and markers land there
