## ADDED Requirements

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
