## MODIFIED Requirements

### Requirement: The server refuses to expose itself without a token
The server SHALL refuse to start when configured to bind a non-loopback
address without a token, and SHALL fail with an error that names the
problem. The failure mode this prevents is severe and silent: an
unauthenticated endpoint on the local network that moves the operator's
mouse, reachable by anything that joins the Wi-Fi. Making it impossible
to configure by accident is worth more than the convenience of allowing
it. Importing the server module SHALL NOT build an application, so
there is no pre-built, unvalidated application for an ASGI server to be
pointed at by import path; an application is built only by the
server's own entry point after its configuration has been validated, or
by an explicit call to the application factory.

#### Scenario: Non-loopback without a token fails at startup
- **WHEN** the server is started bound to a non-loopback address with no
  token configured
- **THEN** it exits with an error identifying that a token is required
  to bind a network-reachable address, and never begins listening

#### Scenario: Loopback without a token remains allowed
- **WHEN** the server is started on loopback with no token configured
- **THEN** it starts normally, since the exposure the token protects
  against does not exist

#### Scenario: Importing the server builds no application
- **WHEN** the server module is imported
- **THEN** no application object exists at module level, so an ASGI
  server cannot be pointed at one that skipped configuration validation
