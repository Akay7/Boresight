## MODIFIED Requirements

### Requirement: Device state is visible without a screen
The firmware SHALL indicate on the board's status LED, with
distinguishable patterns, at least: joining Wi-Fi, connecting to the
server, a configuration or authentication error, streaming with the most
recent reported frame solved, streaming with the most recent reported
frame unsolved, and setup mode (see esp32-cam-setup). The person holding
the gun has no screen, and "is it seeing the markers" is the question
they need answered. The firmware SHALL NOT use the board's high-power
flash LED for status.

#### Scenario: Losing the markers changes the indication
- **WHEN** the device is streaming and the server's telemetry changes
  from a solved frame to an unsolved one
- **THEN** the status LED switches from the solved pattern to the
  unsolved pattern

#### Scenario: An authentication failure is distinguishable
- **WHEN** the server rejects the device's token
- **THEN** the status LED shows the error pattern rather than the
  connecting pattern

#### Scenario: Setup mode is distinguishable
- **WHEN** the device enters setup mode
- **THEN** the status LED shows a pattern different from every other
  state's, for as long as the device stays in setup mode

### Requirement: Secrets are configured outside version control
Wi-Fi credentials, the server address, the token and the trusted
certificate SHALL be supplied as build-time configuration that is
excluded from version control, or, except for the certificate, stored
on the device through setup mode (see esp32-cam-setup). The firmware
project SHALL ship defaults containing no secrets. A setting stored on
the device SHALL take precedence over the build configuration's value
for it. A board with no Wi-Fi network configured either way SHALL enter
setup mode at boot rather than silently fail to connect. The emulator
build, which has no Wi-Fi and does not discover servers, SHALL report a
missing server address at boot.

#### Scenario: A fresh checkout contains no credentials
- **WHEN** the repository is cloned
- **THEN** no Wi-Fi password, token or server certificate is present in
  the firmware project's tracked files

#### Scenario: Missing configuration is reported
- **WHEN** a board is booted with no Wi-Fi SSID configured at build time
  or stored on the device, or the emulator build is booted with no
  server address
- **THEN** the device reports the missing setting on its serial log; the
  board also enters setup mode, and the emulator shows the error pattern

#### Scenario: A stored setting overrides the build configuration
- **WHEN** the build configuration names server port 7331 and port 9100
  is stored on the device
- **THEN** the device connects to port 9100
