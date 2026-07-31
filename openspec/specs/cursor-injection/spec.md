# cursor-injection Specification

## Purpose
TBD - created by archiving change init-server-cursor-injection. Update Purpose after archive.
## Requirements
### Requirement: HTTP endpoint moves the OS cursor to an absolute position
The FastAPI server SHALL expose an HTTP endpoint that accepts a target
position as normalized coordinates (`x`, `y`, each in `[0.0, 1.0]`,
fraction of screen width/height) and SHALL move the OS cursor to the
corresponding absolute screen position via the configured cursor backend.
When a shared token is configured, the endpoint SHALL require it like
every other endpoint, and SHALL move the cursor only for a request that
presents it.

#### Scenario: Valid coordinates move the cursor
- **WHEN** an authorized client sends a move request with `x=0.5, y=0.5`
- **THEN** the server invokes the cursor backend's absolute-move
  operation with coordinates resolving to the center of the screen
- **AND** the response indicates success

#### Scenario: Out-of-range coordinates are rejected
- **WHEN** an authorized client sends a move request with `x` or `y`
  outside `[0.0, 1.0]`
- **THEN** the server responds with a client error (HTTP 422) and does
  not invoke the cursor backend

#### Scenario: Non-numeric coordinates are rejected
- **WHEN** an authorized client sends a move request with a non-numeric
  `x` or `y`
- **THEN** the server responds with a client error (HTTP 422) and does
  not invoke the cursor backend

#### Scenario: An unauthenticated move request moves nothing
- **WHEN** a token is configured and a client sends an otherwise valid
  move request without presenting it
- **THEN** the server refuses the request and does not invoke the cursor
  backend

### Requirement: Cursor movement uses an absolute positioning backend
The system SHALL move the cursor using an absolute-positioning primitive
(not relative deltas), so a single move request places the cursor exactly
at the requested position regardless of where it currently is. On Linux,
this SHALL be implemented via a `uinput` virtual device advertising
absolute `ABS_X`/`ABS_Y` capabilities.

#### Scenario: Cursor jumps rather than drifts
- **WHEN** the cursor is at an arbitrary starting position and a move
  request targets `x=0.1, y=0.1`
- **THEN** the cursor ends at the position corresponding to `x=0.1, y=0.1`
  regardless of its starting position

### Requirement: Cursor backend is swappable for testing
The server SHALL select its cursor backend through a dependency-injection
seam, so automated tests can substitute a fake backend that does not
require a real `uinput` device or OS-level permissions.

#### Scenario: Test suite runs without a real input device
- **WHEN** the pytest suite exercises the move endpoint
- **THEN** it runs to completion and asserts on the fake backend's
  recorded calls, without requiring `/dev/uinput` access

### Requirement: Backend startup fails fast on a broken environment
The server SHALL initialize the cursor backend during application startup
(not on first request) and SHALL fail startup with a clear error if the
backend cannot be initialized (e.g. `uinput` kernel module unavailable or
permission denied).

#### Scenario: Missing uinput permission surfaces at startup
- **WHEN** the server starts on a host where the process cannot open
  `/dev/uinput`
- **THEN** the server fails to start with an error identifying the
  permission problem, rather than starting successfully and failing on
  the first move request
