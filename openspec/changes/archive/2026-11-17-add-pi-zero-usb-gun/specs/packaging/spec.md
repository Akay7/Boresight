# Spec Delta

## ADDED Requirements

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
