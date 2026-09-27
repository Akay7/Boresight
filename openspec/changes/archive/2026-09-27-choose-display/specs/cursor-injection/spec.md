## REMOVED Requirements

### Requirement: The cursor maps onto a configurable display area
**Reason**: Replaced by a display chosen by name on every platform,
which also moves the markers and can be changed from the phone.
**Migration**: Set `view.display` (or `--display`) to the monitor's
name, as listed by `GET /displays`, instead of `BORESIGHT_CURSOR_RECT`.

## ADDED Requirements

### Requirement: The cursor maps onto the chosen display
The normalised `[0.0, 1.0]` coordinates SHALL map onto one display: the
one named by the display setting, or the primary display when none is
named. On Windows and macOS this SHALL be the named monitor's rectangle
in desktop coordinates. On Linux the cursor device SHALL be pinned to
the named output through the compositor where the server knows how
(KDE Plasma's input-device interface, `xinput` on X11). Where it does
not, choosing a display SHALL fail with an error saying the mapping has
to be set in the compositor's own settings, and the cursor SHALL keep
the compositor's mapping. Naming a display the machine does not have
SHALL fail with an error listing the displays it does have.

#### Scenario: A named monitor confines the cursor
- **WHEN** the display `\\.\DISPLAY2`, at desktop `(1920, 0)` and
  1280x1024, is chosen on Windows and a move targets `x=0.0, y=0.0`
- **THEN** the cursor lands at desktop position `(1920, 0)`

#### Scenario: No choice means the primary display
- **WHEN** no display is named
- **THEN** the cursor maps onto the primary display

#### Scenario: KDE pins the device to the output
- **WHEN** the display `HDMI-A-1` is chosen on KDE Plasma under Wayland
- **THEN** the boresight-cursor device's output is set to `HDMI-A-1`
  through KWin

#### Scenario: An unknown display is refused
- **WHEN** a display name the machine does not have is chosen
- **THEN** the choice fails with an error naming the displays available,
  and the previous mapping stays

#### Scenario: A compositor without a known interface is reported
- **WHEN** a display is chosen under a Wayland compositor the server
  cannot pin devices on
- **THEN** the choice fails with an error pointing to the compositor's
  tablet settings
