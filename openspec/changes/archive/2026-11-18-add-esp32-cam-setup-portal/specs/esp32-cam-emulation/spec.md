## ADDED Requirements

### Requirement: Setup mode runs in emulation
The emulator build SHALL enter setup mode on a `setup` console command,
serving the same setup page, validation and storage as a board over its
emulated network instead of a network of its own. The emulator's run
command SHALL make that page reachable from this machine's loopback
interface only. Opening a setup network, the captive name lookup and
the trigger hold at boot remain board-only.

#### Scenario: The setup page is reachable from the host
- **WHEN** `setup` is entered on the emulator console
- **THEN** the setup page can be loaded from a loopback address on this
  machine, and from no other interface

#### Scenario: Settings saved in emulation take effect after restart
- **WHEN** a new token is saved through the setup page of the emulated
  device
- **THEN** the emulated device restarts and presents the new token on
  its next connection to the server

## MODIFIED Requirements

### Requirement: An automated end-to-end check runs the firmware in emulation
The project SHALL provide an automated test suite that boots the emulator
image against a real server using a recording cursor backend and checks:
identification and streaming with solved positions, trigger press and
release, reconnection after the server restarts, presses while
disconnected not being replayed, a refused token being reported and
retried no faster than the back-off allows, and settings saved through
setup mode taking effect after the restart while an invalid submission
changes nothing. The suite SHALL be opt-in, and SHALL be skipped with a
stated reason when the container runtime or the built emulator image is
unavailable, so the default test run is unaffected.

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
