## MODIFIED Requirements

### Requirement: An automated end-to-end check runs the firmware in emulation
The project SHALL provide an automated test suite that boots the emulator
image against a real server using a recording cursor backend and checks:
identification and streaming with solved positions, trigger press and
release, reconnection after the server restarts, presses while
disconnected not being replayed, a refused token being reported and
retried no faster than the back-off allows, settings saved through
setup mode taking effect after the restart while an invalid submission
changes nothing, and a firmware upload through setup mode being
installed while a board image is refused. The suite SHALL be opt-in, and
SHALL be skipped with a stated reason when the container runtime or the
built emulator image is unavailable, so the default test run is
unaffected.

#### Scenario: The suite passes against the emulator image
- **WHEN** the emulator image has been built and the suite is enabled
- **THEN** each check runs against the booted image and passes

#### Scenario: The suite is skipped where it cannot run
- **WHEN** the suite is not enabled, or no emulator image has been built
- **THEN** the default test run skips it and states why

#### Scenario: A refused token is not retried in a tight loop
- **WHEN** the server refuses the emulated device's token
- **THEN** the device reports the refusal on its console and the server
  sees no second attempt within the back-off interval

#### Scenario: A token fixed through setup mode is accepted
- **WHEN** the emulated device is refused for a wrong token, a correct
  token is saved through its setup page, and it restarts
- **THEN** the server accepts its connection and it streams

#### Scenario: An invalid setup submission changes nothing
- **WHEN** a submission with an out-of-range port is posted to the
  emulated device's setup page
- **THEN** the page names the invalid field, nothing is stored, and the
  device stays in setup mode

#### Scenario: A firmware uploaded in setup mode is installed
- **WHEN** an emulator image is uploaded through the emulated device's
  setup page
- **THEN** the device restarts from its other application slot, reports
  the uploaded firmware's version, and streams with its stored settings

#### Scenario: A board image is refused in emulation
- **WHEN** a board image is uploaded through the emulated device's setup
  page
- **THEN** the page says it is not an emulator build and the device
  keeps its firmware
