## MODIFIED Requirements

### Requirement: Setup mode opens when the device has no network configured
On a board, the device SHALL enter setup mode at boot instead of trying
to connect when it has no Wi-Fi network name stored on the device. A
board's firmware brings no network of its own, so a board that has never
been set up, or whose stored settings were erased, always opens setup
mode by itself.

#### Scenario: A freshly flashed board with no settings opens setup
- **WHEN** a board with nothing stored on the device boots
- **THEN** it enters setup mode and reports that on its serial log and
  status LED

#### Scenario: A configured board does not open setup by itself
- **WHEN** a board with a Wi-Fi name stored on the device boots without
  the trigger held
- **THEN** it does not enter setup mode and connects as before

### Requirement: Saved settings take effect after a restart and persist
On a valid save, the device SHALL store the settings in its own flash,
confirm on the page, close the setup network, and restart into normal
operation using them. Stored settings SHALL survive power loss and
reflashing the application. On a board, a network setting not stored on
the device SHALL be unset, except the server port, which SHALL be 7331;
a camera setting not stored SHALL take the value from the build
configuration.

#### Scenario: A saved token is used after restart
- **WHEN** a new token is saved in setup mode
- **THEN** the device restarts, and its next connection to the server
  presents the new token

#### Scenario: Settings survive a power cycle
- **WHEN** the device is powered off and on after settings were saved
- **THEN** it uses the saved settings without entering setup mode

#### Scenario: An unset port is 7331
- **WHEN** a board's Wi-Fi network and token are saved with the port
  left at its shown value and no port was ever stored
- **THEN** the board connects to the server on port 7331

### Requirement: The device can be reset to its build defaults
The setup page SHALL offer to erase every setting stored on the device,
after which the device SHALL restart. On a board this leaves it with no
network configured, so it opens setup mode by itself, with the camera
settings back at their build configuration's values.

#### Scenario: Erasing stored settings restores the build defaults
- **WHEN** the user chooses to reset a board to its build defaults
- **THEN** the stored settings are erased, the board restarts into setup
  mode by itself, and its page shows no network set and the build
  configuration's camera values
