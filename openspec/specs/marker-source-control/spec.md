# marker-source-control Specification

## Purpose
Let the marker source — printed or on-screen — be chosen while the
system is running, instead of via a startup flag and a manual restart.
This covers the overlay process's lifecycle under the server's control,
the handshake that keeps the drawn and solved layouts identical,
switching the live pipeline without dropping a connected client, and
reporting the current state and any failure to the caller.

## Requirements
### Requirement: The marker source can be chosen while the system runs
The system SHALL expose the current marker source and allow it to be
changed between printed and on-screen markers without restarting the
server, and SHALL report the resulting state to the caller. A change
SHALL take effect for frames arriving after it, including on a client
that is already connected and streaming.

#### Scenario: Reading the current source
- **WHEN** a client asks for the marker source
- **THEN** the system reports which source is active

#### Scenario: Switching reaches an already-connected client
- **WHEN** a phone is connected and streaming, and the marker source is
  changed
- **THEN** frames arriving after the change are solved against the newly
  selected layout
- **AND** the phone's connection is not closed or interrupted

#### Scenario: Switching back restores the previous behaviour
- **WHEN** the source is changed to on-screen markers and then back to
  printed
- **THEN** the system solves against the printed layout exactly as it
  did before either change

### Requirement: Selecting on-screen markers starts the overlay
Selecting on-screen markers SHALL start the marker overlay on the
server's display, and selecting printed markers SHALL stop it. The
system SHALL NOT report on-screen markers as active unless the overlay
is actually running.

#### Scenario: Selecting on-screen markers puts tags on the display
- **WHEN** a client selects on-screen markers and the display
  environment can host the overlay
- **THEN** the overlay process is started and the reported state shows
  on-screen markers as active

#### Scenario: Selecting printed markers removes them
- **WHEN** a client selects printed markers while the overlay is running
- **THEN** the overlay process is stopped and the reported state shows
  printed markers as active

#### Scenario: Selecting the active source again changes nothing
- **WHEN** a client selects the source that is already active
- **THEN** the overlay is neither restarted nor stopped, and the
  reported state is unchanged

### Requirement: The overlay reports the geometry it used
The overlay SHALL report the display size, tag size and inset it
actually rendered with, and the system SHALL build the solver's layout
from those reported values. The system SHALL NOT require a display
resolution to be supplied by hand, and SHALL NOT assume one.

#### Scenario: The solved layout is built from what was drawn
- **WHEN** the overlay starts and reports its geometry
- **THEN** the layout the solver uses is derived from exactly that
  geometry, so the drawn and solved positions are identical

#### Scenario: A resolution is never guessed
- **WHEN** on-screen markers are selected without any resolution being
  configured
- **THEN** the system still produces a correct layout, taken from the
  overlay rather than assumed

### Requirement: A failed overlay is reported as a failure
The system SHALL leave printed markers active where the overlay cannot
start — an unsupported display environment, its optional dependencies
absent, no reachable display, or the process exiting immediately — and
SHALL report the failure with the overlay's own explanation. It SHALL
NOT report on-screen markers as active, and SHALL remain able to serve
requests and continue solving.

#### Scenario: An unsupported environment does not silently switch
- **WHEN** on-screen markers are selected on a machine where the overlay
  refuses to start
- **THEN** the reported state still shows printed markers as active
- **AND** the failure is reported to the caller, carrying the overlay's
  explanation of why it refused

#### Scenario: The system keeps working after a failed selection
- **WHEN** a selection of on-screen markers has failed
- **THEN** frames continue to be solved against the printed layout, and
  the marker source can be selected again

#### Scenario: An overlay that dies is noticed
- **WHEN** the overlay process exits on its own while on-screen markers
  are active
- **THEN** the reported state no longer claims on-screen markers are
  active

### Requirement: The overlay never outlives the server
The system SHALL terminate the overlay process when the server shuts
down, and SHALL NOT leave it running. This matters more than it
usually would: the overlay window is input-transparent, takes no
keyboard focus and has no title bar, so it cannot be dismissed by
clicking or closing it — an orphaned overlay is genuinely difficult for
a user to remove.

#### Scenario: Server shutdown removes the tags
- **WHEN** the server shuts down while the overlay is running
- **THEN** the overlay process is terminated

#### Scenario: Only one overlay runs at a time
- **WHEN** on-screen markers are selected while an overlay started by
  this system is already running
- **THEN** a second overlay process is not left running alongside it

### Requirement: Starting a process is an authenticated action with a fixed command
The endpoints that change the marker source SHALL require the same
token as every other endpoint, and the command used to start the
overlay SHALL be fixed rather than composed from request content. Any
caller-supplied value SHALL be validated as the type it is meant to be
before use.

#### Scenario: An unauthenticated client cannot start the overlay
- **WHEN** a token is configured and a client attempts to change the
  marker source without presenting it
- **THEN** the request is refused and no process is started

#### Scenario: Request content cannot influence the command
- **WHEN** the marker source is changed
- **THEN** the overlay is started from a fixed command, with no argument
  taken verbatim from the request body
