## Purpose

Lets the ESP32-CAM firmware be built without a locally installed toolchain
and exercised end to end in an open-source emulator, against a real server,
so everything above the camera sensor and radio is verified without a board.

## ADDED Requirements

### Requirement: The firmware builds without a local toolchain
The project SHALL provide a single command that builds the firmware inside
a pinned ESP-IDF container image, requiring only a container runtime on the
host. It SHALL build either the device image or the emulator image, and
the files it produces SHALL be owned by the invoking user rather than by
the container's user.

#### Scenario: The device image builds from a fresh checkout
- **WHEN** the build command is run for the device profile in a checkout
  with no local configuration
- **THEN** the build succeeds using only the tracked defaults

#### Scenario: Build output belongs to the user
- **WHEN** a build has completed
- **THEN** the build directory and any fetched components are owned by the
  user who ran it and can be deleted without elevated permissions

### Requirement: The emulator build is kept apart from the device build
The emulator image SHALL be built from its own configuration into its own
build directory, so that building it never changes the device
configuration and a device build never contains the emulator's
substitutes. An emulator image SHALL announce at boot, and in the version
it reports in `hello`, that it is an emulator build.

#### Scenario: Building the emulator leaves the device configuration alone
- **WHEN** the emulator image is built after the device has been configured
- **THEN** the device configuration file and build directory are unchanged

#### Scenario: An emulator session is identifiable on the server
- **WHEN** the emulator image connects to the server
- **THEN** the session's reported client kind is the device's, and its
  reported version marks it as an emulator build

### Requirement: A fixture is rendered as the ESP32-CAM sees the scene
The project SHALL provide a checked-in rendered frame sequence of the same
scene and camera path as the existing synthetic video fixture, rendered at
the firmware's default capture resolution and aspect ratio, through a lens
matching the device's stock field of view, with sensor noise and JPEG
compression representative of the device. Each frame SHALL carry its
ground-truth aim point, and the generator SHALL record every rendering and
degradation parameter in the fixture's manifest. Producing it SHALL leave
the existing fixture unchanged.

#### Scenario: The device fixture is generated alongside the existing one
- **WHEN** the generator is run with the device profile
- **THEN** it writes the device fixture and its manifest, and the existing
  fixture's files are byte-for-byte unchanged

#### Scenario: Aim accuracy is measured at the device's resolution
- **WHEN** the replay accuracy tests run
- **THEN** they run against the device fixture as well as the existing one,
  each against tolerances recorded for that fixture, and report every frame
  solved within them

### Requirement: Recorded frames stand in for the camera sensor
In the emulator build, the camera sensor SHALL be replaced by a source that
serves frames of the device fixture in order, repeating, through
the same capture, pacing and send path the sensor's frames take. The capture
resolution reported in `hello` SHALL be read from the frames themselves. The
build SHALL fail, naming the file, when a fixture is not a JPEG — the
symptom of a Git LFS pointer that was never fetched.

#### Scenario: The server solves the device's frames as it solves the replay
- **WHEN** the emulator image streams its frames to the server
- **THEN** every solved position the server reports equals a position the
  same fixture frames produce when replayed through the pipeline directly

#### Scenario: The reported resolution matches the frames
- **WHEN** the emulator image says `hello`
- **THEN** the frame size it reports is the pixel size of the fixture frames

#### Scenario: An unfetched fixture fails the build
- **WHEN** a fixture file is a Git LFS pointer rather than a JPEG
- **THEN** the emulator build fails with a message naming the file and how
  to fetch it

### Requirement: The emulated device reaches a local server without exposing it
The emulator SHALL reach a server listening only on this machine's loopback
interface, with no tunnel, port forward to the network or public endpoint.

#### Scenario: A loopback-only server is reached
- **WHEN** the server is bound to 127.0.0.1 and the emulator image is run
- **THEN** the emulated device connects to it and streams frames

### Requirement: Buttons can be operated from the emulator console
The emulator build SHALL accept commands on its serial console that set a
button's level to pressed or released, and SHALL feed that level through the
same debouncing, press/release and send logic the GPIO level feeds on a
board. Only reading the pin is replaced.

#### Scenario: A console press and release hold and release the trigger
- **WHEN** `press` is entered on the console, and `release` some time later
- **THEN** the server holds its button from the press until the release

#### Scenario: A console press while disconnected is not replayed
- **WHEN** `press` and `release` are entered while the device is not
  connected, and the connection is later re-established
- **THEN** the server receives no trigger for them

### Requirement: Link-state changes are written to the console
The firmware SHALL write a line to its console each time its link state
changes — joining the network, connecting to the server, streaming, error —
on hardware and in emulation alike, so that the state the LED shows can
also be read and asserted on.

#### Scenario: Reaching the server is logged
- **WHEN** the device connects to the server and begins streaming
- **THEN** a line recording the change to the streaming state appears on
  the console

### Requirement: An automated end-to-end check runs the firmware in emulation
The project SHALL provide an automated test suite that boots the emulator
image against a real server using a recording cursor backend and checks:
identification and streaming with solved positions, trigger press and
release, reconnection after the server restarts, presses while
disconnected not being replayed, and a refused token being reported and
retried no faster than the back-off allows. The suite SHALL be opt-in,
and SHALL be skipped with a stated reason when the container runtime or
the built emulator image is unavailable, so the default test run is
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
