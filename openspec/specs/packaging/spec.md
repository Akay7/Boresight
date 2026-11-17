# packaging Specification

## Purpose
Defines which Python versions the Boresight package supports and the
commands an installed copy provides, so that an install works the same
way as running from a checkout.

## Requirements

### Requirement: The package supports Python 3.12 and later
The package SHALL declare Python 3.12 as its minimum version and SHALL
install and pass its test suite on Python 3.12 and on the newest Python
it is developed on. Its source SHALL NOT use syntax or standard-library
APIs newer than its declared minimum.

#### Scenario: Installing on Python 3.12
- **WHEN** the package is installed and its tests are run on Python 3.12
- **THEN** it installs, and the test suite passes

### Requirement: An install provides the server and overlay as commands
Installing the package SHALL provide a `boresight` command that runs the
same program as `python -m boresight.server`, and a `boresight-overlay`
command that runs the same program as `python -m boresight.overlay`,
with the same arguments and the same validation. The `python -m` forms
SHALL keep working.

#### Scenario: Starting the server by its command
- **WHEN** a user runs `boresight --host 0.0.0.0` with no token
- **THEN** it refuses to start exactly as `python -m boresight.server
  --host 0.0.0.0` does

#### Scenario: Starting the overlay by its command
- **WHEN** a user runs `boresight-overlay --help`
- **THEN** it prints the overlay's usage, as `python -m
  boresight.overlay --help` does

### Requirement: The server runs without Linux-only modules
The server, pipeline and marker-source modules SHALL import, and the
server SHALL start, on a system where Linux-only modules (evdev,
`fcntl`) and the optional overlay toolkit are absent. Those modules
SHALL be imported only by the code paths that need them. The marker
overlay MAY be unavailable on such a platform, and where it is SHALL
refuse to start with its existing message naming printed markers.

#### Scenario: Importing the server without Linux-only modules
- **WHEN** the server, pipeline and marker-source modules are imported
  with evdev, `fcntl` and the overlay toolkit unimportable
- **THEN** the imports succeed

#### Scenario: The platform-independent tests run on Windows and macOS
- **WHEN** continuous integration runs
- **THEN** the platform-independent tests, including the Windows and
  macOS backend tests, run and pass on Windows and macOS runners

### Requirement: The aim pipeline installs without the server's dependencies
The package SHALL allow the aim pipeline -- detection, marker map, solve,
smoothing, aim-hold, lens and zero models and the cursor backend
interface -- to be installed and imported with only NumPy and OpenCV,
without the web server, TLS-certificate and QR-code dependencies. A
default development sync SHALL still install everything, so the test
suite is unchanged.

#### Scenario: Importing the pipeline in a minimal environment
- **WHEN** the package is installed with only its core dependencies and
  the aim pipeline is imported
- **THEN** the import succeeds without the web, TLS or QR libraries

#### Scenario: The default sync is unchanged
- **WHEN** a developer runs the default sync and the test suite
- **THEN** all dependencies are present and the tests pass

### Requirement: An install provides the gun as a command
Installing the package SHALL provide a `boresight-gun` command that runs
the same program as `python -m boresight.gun`, with the same arguments.

#### Scenario: Starting the gun by its command
- **WHEN** a user runs `boresight-gun --help`
- **THEN** it prints the same usage as `python -m boresight.gun --help`
