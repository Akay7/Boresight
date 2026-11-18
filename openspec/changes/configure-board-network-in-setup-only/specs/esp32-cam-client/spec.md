## MODIFIED Requirements

### Requirement: Secrets are configured outside version control
On a board, the Wi-Fi network name and password, the server address and
port, and the token SHALL come only from settings stored on the device
through setup mode (see esp32-cam-setup); a board's build configuration
SHALL offer none of them, and a board's firmware image SHALL contain
none of them. The trusted certificate SHALL be supplied as build-time
configuration excluded from version control. The firmware project SHALL
ship defaults containing no secrets. A board with no Wi-Fi network
stored SHALL enter setup mode at boot rather than silently fail to
connect. The emulator build, which has no Wi-Fi and does not discover
servers, SHALL take its server address, port and token from its build
configuration, SHALL let settings stored through its setup page take
precedence over them, and SHALL report a missing server address at
boot.

#### Scenario: A fresh checkout contains no credentials
- **WHEN** the repository is cloned
- **THEN** no Wi-Fi password, token or server certificate is present in
  the firmware project's tracked files

#### Scenario: A board's build configuration has no network settings
- **WHEN** the board firmware's build configuration is opened
- **THEN** it offers no Wi-Fi name or password, server address, port or
  token, and a board image built from it contains none of them

#### Scenario: Missing configuration is reported
- **WHEN** a board is booted with no Wi-Fi network stored on the device,
  or the emulator build is booted with no server address
- **THEN** the device reports the missing setting on its serial log; the
  board also enters setup mode, and the emulator shows the error pattern

#### Scenario: A stored setting overrides the emulator's build configuration
- **WHEN** the emulator's build configuration names server port 7391 and
  port 9100 is stored on the emulated device
- **THEN** the emulated device connects to port 9100
