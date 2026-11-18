# esp32-cam-setup Specification

## Purpose
Lets the ESP32-CAM's network, server and camera settings be changed on
the device itself, from a phone, through a temporary setup network it
opens, with no rebuild, reflash or USB-serial adapter.

## Requirements

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

### Requirement: Holding the trigger at boot opens setup mode
The device SHALL enter setup mode when the trigger button is held down
from power-on or reset for at least 5 seconds, whether or not it is
configured. A press shorter than that, or one starting after boot, SHALL
NOT enter setup mode. The status LED SHALL switch to the setup pattern
once the hold has lasted long enough, so the person holding it knows to
let go.

#### Scenario: A 5-second hold at power-on opens setup
- **WHEN** the trigger is held while the device powers on and kept held
  for 5 seconds
- **THEN** the status LED shows the setup pattern and the device enters
  setup mode

#### Scenario: A short hold at boot starts normally
- **WHEN** the trigger is held at power-on and released after 2 seconds
- **THEN** the device starts normally and does not enter setup mode

#### Scenario: Pressing the trigger later does not open setup
- **WHEN** a running device's trigger is held for 10 seconds
- **THEN** it is an ordinary trigger hold and the device stays out of
  setup mode

### Requirement: Setup mode offers its own temporary network
In setup mode the device SHALL stop its normal connection and camera
stream and open a Wi-Fi network of its own, named `Boresight-` followed
by four hexadecimal digits from the device's MAC address, with no
password. The network SHALL exist only while the device is in setup
mode.

#### Scenario: The setup network can be joined
- **WHEN** the device is in setup mode
- **THEN** a network named `Boresight-` and four hex digits is visible,
  and a phone can join it without a password

#### Scenario: Setup mode does not stream
- **WHEN** the device enters setup mode
- **THEN** it does not connect to the server or send frames until it
  leaves setup mode

### Requirement: The setup page opens when a phone joins
The device SHALL serve its setup page to any device on its setup
network, at the address it gives itself and in answer to any web
address requested, and SHALL answer every name lookup on that network
with its own address, so that a phone's sign-in check opens the page
without the user typing an address.

#### Scenario: A phone's sign-in check shows the page
- **WHEN** a phone joins the setup network and checks for internet
  access
- **THEN** it is led to the setup page

#### Scenario: Any address reaches the page
- **WHEN** a browser on the setup network opens any web address
- **THEN** it receives the setup page

### Requirement: The setup page edits the device's settings
The setup page SHALL let the user view and change the Wi-Fi network name
and password, the server address and port, the token, and the camera's
resolution, JPEG quality, frame-rate cap, exposure and gain, and SHALL
show the value currently in effect for each one that is not secret. It
SHALL offer a list of the Wi-Fi networks the device can see. The server
address MAY be left empty, which means "find the server on the network"
(see server-discovery).

#### Scenario: The page shows current settings
- **WHEN** the setup page is opened on a device configured for server
  port 7331 and 1024x768
- **THEN** the page shows port 7331 and 1024x768 as the current values

#### Scenario: Nearby networks are offered
- **WHEN** the setup page is opened
- **THEN** it lists the names of Wi-Fi networks in range for the user to
  pick from, and still allows typing a name that is not listed

### Requirement: Secrets are never sent back to the page
The device SHALL NOT include a stored Wi-Fi password or token in
anything it serves. The page SHALL say whether each is set. Submitting
either field empty SHALL keep the stored value, and the page SHALL offer
an explicit way to clear it.

#### Scenario: A stored token is not shown
- **WHEN** the setup page is opened on a device with a token stored
- **THEN** the page states that a token is set, and neither the page
  nor any response from the device contains the token's value

#### Scenario: An empty secret field keeps the stored one
- **WHEN** the user changes only the server port and saves with the
  password and token fields left empty
- **THEN** the device keeps its stored Wi-Fi password and token

### Requirement: Settings are validated before anything is stored
The device SHALL check every submitted value before storing any: the
network name 1 to 32 bytes, the password empty or 8 to 63 characters,
the port 1 to 65535, the address empty or a valid host name or IPv4
address, and each camera setting within the range its build
configuration allows. If any value fails, the device SHALL store
nothing, stay in setup mode, and show the page again naming each
invalid field.

#### Scenario: An invalid port changes nothing
- **WHEN** the user saves with port 70000 and a new token
- **THEN** neither the port nor the token is stored, and the page names
  the port as invalid

#### Scenario: A valid submission is accepted
- **WHEN** the user saves a network name, an 8-character password, an
  empty address and port 7331
- **THEN** the settings are stored and the device confirms on the page
  that it is restarting

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

### Requirement: The setup network closes on its own
If nothing has been saved 10 minutes after setup mode began, the device
SHALL close the setup network. A device with a network configured SHALL
then restart into normal operation with its settings unchanged. A device
with none SHALL stop with the error pattern until it is reset or power
cycled.

#### Scenario: An abandoned setup returns a configured board to work
- **WHEN** a configured board is put in setup mode and left for 10
  minutes with nothing saved
- **THEN** the setup network disappears and the board reconnects to the
  server with its previous settings

#### Scenario: An unconfigured board does not keep its network open
- **WHEN** an unconfigured board's setup network has been open for 10
  minutes with nothing saved
- **THEN** the network disappears and the status LED shows the error
  pattern until the board is reset
