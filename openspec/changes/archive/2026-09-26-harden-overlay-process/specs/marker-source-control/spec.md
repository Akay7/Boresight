## ADDED Requirements

### Requirement: Marker-source changes are serialized
The system SHALL apply changes to the marker source — selecting a
source and changing the overlay margin — one at a time, so that
requests arriving concurrently behave as if they had arrived in some
order. Selecting the source that is already active, or setting the
overlay margin to the value already in effect, SHALL change nothing.
Reading the marker source SHALL NOT wait for a change in progress; it
SHALL report that a change is in progress instead.

#### Scenario: Two quick selections start one overlay
- **WHEN** two requests to select on-screen markers arrive at the same
  time while printed markers are active
- **THEN** exactly one overlay process is started, both requests report
  on-screen markers as active, and no other overlay process is left
  running

#### Scenario: A selection and a margin change do not interleave
- **WHEN** a request to select on-screen markers and a request to change
  the overlay margin arrive at the same time
- **THEN** at most one overlay process is running afterwards, and it is
  the one the controller reports

#### Scenario: Setting the margin already in effect changes nothing
- **WHEN** on-screen markers are active and a client sets the overlay
  margin to the value already in effect
- **THEN** the overlay is not restarted

#### Scenario: Reading the state during a switch does not block
- **WHEN** a client reads the marker source while a switch is still
  waiting for the overlay to start
- **THEN** the read returns promptly and reports that a switch is in
  progress

### Requirement: The overlay's output cannot stall it
The system SHALL continuously consume everything the overlay process
writes, on both its output channels, for as long as the process runs,
so that no amount of output can cause the overlay to block. The system
SHALL keep only a bounded amount of that output, SHALL make it
available to the server's log, and SHALL use the most recent output as
the overlay's explanation when it fails.

#### Scenario: A chatty overlay keeps running
- **WHEN** the overlay writes far more diagnostic output than an
  operating-system pipe can buffer, before or after reporting its
  geometry
- **THEN** the overlay is not blocked, its geometry is still received,
  and on-screen markers become active

#### Scenario: The explanation survives a lot of output
- **WHEN** the overlay writes a large amount of output and then exits
  with an explanation as its last words
- **THEN** the failure reported to the caller carries that explanation
  and is bounded in size

## MODIFIED Requirements

### Requirement: A failed overlay is reported as a failure
The system SHALL leave printed markers active where the overlay cannot
start — an unsupported display environment, its optional dependencies
absent, no reachable display, or the process exiting immediately — and
SHALL report the failure with the overlay's own explanation. It SHALL
NOT report on-screen markers as active, and SHALL remain able to serve
requests and continue solving. Where an overlay that was running exits
on its own, the reported error SHALL include the last thing it wrote,
if it wrote anything.

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
- **AND** the reported error includes the overlay's last line of output,
  where it wrote one

### Requirement: The overlay never outlives the server
The system SHALL terminate the overlay process when the server shuts
down, and SHALL NOT leave it running. This matters more than it
usually would: the overlay window is input-transparent, takes no
keyboard focus and has no title bar, so it cannot be dismissed by
clicking or closing it — an orphaned overlay is genuinely difficult for
a user to remove. Shutdown SHALL NOT race a switch in progress: an
overlay still starting when shutdown begins SHALL be stopped, and no
overlay SHALL be started once shutdown has begun.

#### Scenario: Server shutdown removes the tags
- **WHEN** the server shuts down while the overlay is running
- **THEN** the overlay process is terminated

#### Scenario: Only one overlay runs at a time
- **WHEN** on-screen markers are selected while an overlay started by
  this system is already running
- **THEN** a second overlay process is not left running alongside it

#### Scenario: Shutdown during a start
- **WHEN** the server shuts down while an overlay has been started but
  has not yet reported its geometry
- **THEN** that overlay process is terminated without waiting out the
  geometry timeout, and the pending selection fails

#### Scenario: No start after shutdown
- **WHEN** on-screen markers are selected after shutdown has begun
- **THEN** no overlay process is started and the selection fails
