## MODIFIED Requirements

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
