## ADDED Requirements

### Requirement: A session can identify its client kind
The server SHALL accept a `hello` JSON control message on the frame
connection's text channel carrying the client kind and, optionally, its
software version and capture resolution, and SHALL attach that identity
to the session for its logs and its entry in the session listing. A
session that never sends `hello` SHALL be served exactly as before and
labelled as unidentified. A malformed `hello` SHALL be ignored without
closing the connection, and SHALL NOT affect frame handling.

#### Scenario: An identified session is logged by kind
- **WHEN** a client sends `hello` with client kind `esp32-cam` and then
  streams frames
- **THEN** the server's connection, periodic and disconnection log lines
  for that session name the client kind

#### Scenario: A session that never says hello is unaffected
- **WHEN** a client streams frames without sending `hello`
- **THEN** frames are processed and reported exactly as before, and the
  session is listed as unidentified

#### Scenario: A malformed hello is ignored
- **WHEN** a client sends a `hello` message with a missing or non-string
  client kind
- **THEN** the connection stays open, the session remains unidentified,
  and subsequent frames are processed normally

### Requirement: Active sessions' telemetry is readable over HTTP
The server SHALL serve a listing of the currently active frame sessions,
each with its client identity, its remote address, how long it has been
connected, and the same telemetry fields most recently sent to that
client over its own socket, excluding debug geometry. A client with no
display of its own cannot show its telemetry, so it SHALL be observable
from another device. A session SHALL disappear from the listing once its
connection ends, and the listing SHALL be covered by the same token
requirement as every other endpoint.

#### Scenario: A streaming session appears in the listing
- **WHEN** a client is connected and has streamed frames, and the session
  listing is requested
- **THEN** the listing contains that session with its client kind,
  connection age, frame counts, round-trip time and most recent outcome

#### Scenario: A closed session leaves the listing
- **WHEN** a client disconnects and the listing is requested afterwards
- **THEN** that session is no longer present

#### Scenario: Debug geometry is not exposed in the listing
- **WHEN** a session with debug geometry enabled is listed
- **THEN** its listing entry carries no debug geometry

#### Scenario: The listing requires the token
- **WHEN** a token is configured and the listing is requested without it
- **THEN** the request is refused
