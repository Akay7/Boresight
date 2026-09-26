# cursor-injection Specification

## Purpose
Moves the OS cursor to an absolute position and presses, holds and
releases its primary button, behind a backend interface that tests can
replace and that fails fast when the device cannot be opened.

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
absolute `ABS_X`/`ABS_Y` capabilities. On Windows, it SHALL be
implemented with absolute pointer input addressed in virtual-desktop
coordinates, so a target on any monitor — including one left of or
above the primary — is reachable. On macOS, it SHALL be implemented with
pointer events located in global display coordinates. On Windows the
server SHALL read display geometry in physical pixels, unaffected by
display scaling.

#### Scenario: Cursor jumps rather than drifts
- **WHEN** the cursor is at an arbitrary starting position and a move
  request targets `x=0.1, y=0.1`
- **THEN** the cursor ends at the position corresponding to `x=0.1, y=0.1`
  regardless of its starting position

#### Scenario: A Windows move lands on the exact pixel
- **WHEN** on Windows a move targets a normalised position that
  corresponds to a given pixel of the target display area
- **THEN** the absolute input sent resolves, under Windows' own
  conversion, to exactly that pixel, for every pixel of the virtual
  desktop

#### Scenario: A monitor with a negative origin is reachable
- **WHEN** the target display area lies left of the primary monitor
- **THEN** moves to `x=0.0` and `x=1.0` land on that area's left and
  right edges

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
permission denied on Linux, the permission to post input events not
granted on macOS, or a platform with no backend at all).

#### Scenario: Missing uinput permission surfaces at startup
- **WHEN** the server starts on a host where the process cannot open
  `/dev/uinput`
- **THEN** the server fails to start with an error identifying the
  permission problem, rather than starting successfully and failing on
  the first move request

#### Scenario: Missing macOS Accessibility permission surfaces at startup
- **WHEN** the server starts on macOS without permission to post input
  events
- **THEN** it fails to start with an error naming the Accessibility
  setting where the permission is granted and that the server must be
  restarted afterwards, rather than starting and having every event
  silently dropped

#### Scenario: An unsupported platform surfaces at startup
- **WHEN** the server starts on a platform with no cursor backend
- **THEN** it fails to start with an error naming the platform

### Requirement: The cursor backend can hold and release the primary button
The cursor backend interface SHALL expose press and release operations,
distinct from click, that respectively press and release the primary
button at the cursor's current position without moving it. Absolute
movement between a press and a release SHALL move the cursor with the
button held; on macOS such movement SHALL be reported to applications as
a drag rather than as plain movement. A click SHALL be equivalent to a
press immediately followed by a release. On Linux the button SHALL be
the same one a click uses, so a hold and a click land on the same
pointer as the cursor movement. On Windows and macOS the button SHALL be
the left mouse button. Closing the backend SHALL release a button still
held.

#### Scenario: A press, a move and a release are a drag
- **WHEN** press is invoked, then absolute movement to a new position,
  then release
- **THEN** the OS observes the button going down at the old position,
  the cursor moving with it held, and the button going up at the new
  position

#### Scenario: A macOS move while held is a drag event
- **WHEN** on macOS the button is pressed and the cursor then moved
- **THEN** the move is posted as a left-button drag, and a move after
  release is posted as plain movement again

#### Scenario: Closing releases a held button
- **WHEN** the backend is closed while the button is held
- **THEN** the OS observes the button released

#### Scenario: A fake backend records holds
- **WHEN** a test presses and releases against a fake backend
- **THEN** the fake records the press and the release, without
  `/dev/uinput` access

### Requirement: The cursor backend supports a discrete click
The cursor backend interface SHALL expose a click operation, distinct
from absolute movement, that presses and releases the primary button at
the cursor's current position. On Linux, the click SHALL be delivered on
the same pointer that absolute movement positions, so that it lands
where the cursor is shown, including under a Wayland compositor where
each input device can have its own pointer position. The button SHALL
never go down as a side effect of movement, so positioning alone never
clicks.

#### Scenario: A click presses and releases the primary button
- **WHEN** the cursor backend's click operation is invoked
- **THEN** the OS observes a primary-button press followed by a release
  at the cursor's current position, with no change to that position

#### Scenario: A click does not move the cursor
- **WHEN** the cursor is at an arbitrary position and the click
  operation is invoked
- **THEN** the cursor remains at that position after the click
  completes

### Requirement: Click backend is swappable for testing
The cursor backend's click operation SHALL be substitutable the same
way absolute movement already is, so automated tests can assert a click
occurred without a real `uinput` device or OS-level permissions.

#### Scenario: Test suite asserts a click without a real input device
- **WHEN** a test invokes the click operation against a fake backend
- **THEN** the fake backend records that a click occurred, without
  requiring `/dev/uinput` access

### Requirement: The cursor backend is chosen by platform
The server's default cursor backend SHALL be selected from the platform
it runs on — `uinput` on Linux, the Windows backend on Windows, the
macOS backend on macOS — with the same interface and the same
behaviour above it (smoothing, holding, ownership, trigger timing).
The platform-specific operating-system calls SHALL sit behind a
replaceable layer, so the events each backend constructs can be tested
on any platform without sending real input.

#### Scenario: Each platform gets its own backend
- **WHEN** the default backend is created on Linux, Windows or macOS
- **THEN** the backend for that platform is created

#### Scenario: Event construction is testable without the OS
- **WHEN** a test drives the Windows or macOS backend against a
  recording replacement of its platform layer
- **THEN** it can assert the exact events sent, on a Linux host

### Requirement: Relative deltas are available on every platform
When `BORESIGHT_REL_SCALE` is set to a non-zero value, each backend SHALL
also report the change in position since the previous move as relative
pointer motion, scaled by that value, while still placing the cursor
absolutely. The first move SHALL report no delta. With the variable
unset, no relative motion SHALL be reported.

#### Scenario: A second move carries a scaled delta
- **WHEN** `BORESIGHT_REL_SCALE` is `1000` and the cursor moves from
  `x=0.5` to `x=0.6`
- **THEN** a relative motion of 100 units in x is reported alongside the
  absolute placement at `x=0.6`

#### Scenario: Relative motion is off by default
- **WHEN** `BORESIGHT_REL_SCALE` is unset and the cursor moves twice
- **THEN** no relative motion is reported

### Requirement: The cursor maps onto a configurable display area
On Windows and macOS the normalised `[0.0, 1.0]` coordinates SHALL map
onto the primary display by default. Setting `BORESIGHT_CURSOR_RECT` to
`x,y,width,height` (in the platform's desktop coordinates) SHALL map
them onto that rectangle instead, so the cursor can be confined to the
monitor the markers surround. A malformed value SHALL fail backend
startup with an error showing the expected form.

#### Scenario: A configured rectangle confines the cursor
- **WHEN** `BORESIGHT_CURSOR_RECT` is `1920,0,1280,1024` and a move
  targets `x=0.0, y=0.0`
- **THEN** the cursor lands at desktop position `(1920, 0)`

#### Scenario: A malformed rectangle is rejected at startup
- **WHEN** `BORESIGHT_CURSOR_RECT` is `wide`
- **THEN** the backend fails to start with an error showing the
  `x,y,width,height` form
