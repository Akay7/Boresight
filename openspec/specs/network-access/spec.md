# network-access Specification

## Purpose
TBD - created by archiving change add-phone-video-stream. Update Purpose after archive.
## Requirements
### Requirement: The server can be reached from another device on the network
The server SHALL accept a configurable bind address, and SHALL continue
to default to loopback. A phone is a separate device and cannot reach
loopback at all, so serving it requires binding to an address the LAN
can route to — but that SHALL be an explicit choice, never the default.

#### Scenario: Loopback remains the default
- **WHEN** the server is started with no bind address configured
- **THEN** it binds to loopback only and is not reachable from other
  devices

#### Scenario: A LAN address can be selected explicitly
- **WHEN** the server is started with a non-loopback bind address
  configured
- **THEN** it listens on that address, so a phone on the same network
  can reach it

### Requirement: Every endpoint requires a shared token when one is configured
When a token is configured, the server SHALL require it on every
request it serves — the client page, the marker sheets, the cursor
endpoint, and the frame socket — and SHALL reject requests without a
valid token. Tokens SHALL be compared in a way that does not leak their
contents through timing.

#### Scenario: An unauthenticated request is rejected
- **WHEN** a token is configured and a client requests any endpoint
  without it
- **THEN** the server refuses the request and performs no action on its
  behalf

#### Scenario: An unauthenticated socket is closed rather than served
- **WHEN** a token is configured and a client opens the frame socket
  without presenting it
- **THEN** the server closes the connection with a policy-violation
  status and processes no frames from it

#### Scenario: A valid token is served normally
- **WHEN** a token is configured and a client presents it
- **THEN** the request is served exactly as it would be with no token
  configured

### Requirement: The server refuses to expose itself without a token
The server SHALL refuse to start when configured to bind a non-loopback
address without a token, and SHALL fail with an error that names the
problem. The failure mode this prevents is severe and silent: an
unauthenticated endpoint on the local network that moves the operator's
mouse, reachable by anything that joins the Wi-Fi. Making it impossible
to configure by accident is worth more than the convenience of allowing
it.

#### Scenario: Non-loopback without a token fails at startup
- **WHEN** the server is started bound to a non-loopback address with no
  token configured
- **THEN** it exits with an error identifying that a token is required
  to bind a network-reachable address, and never begins listening

#### Scenario: Loopback without a token remains allowed
- **WHEN** the server is started on loopback with no token configured
- **THEN** it starts normally, since the exposure the token protects
  against does not exist

### Requirement: The server can serve over TLS
The server SHALL support serving over TLS with a supplied or generated
certificate. This is not optional polish: browsers expose camera capture
only in a secure context, and a LAN IP over plain HTTP is not one, so
without TLS the phone client cannot access the camera at all. Where a
certificate is generated rather than supplied, it SHALL be persisted and
reused across restarts, so the phone's acceptance of it survives.

#### Scenario: A generated certificate is reused across restarts
- **WHEN** the server is started with TLS enabled and no certificate has
  been supplied
- **THEN** it generates one, persists it, and reuses the same
  certificate on subsequent starts rather than generating a new one

#### Scenario: A supplied certificate is used as given
- **WHEN** the server is started with a certificate and key supplied
- **THEN** it serves TLS using them and generates nothing

### Requirement: Startup reports the address the phone should open
The server SHALL print, at startup, the complete URL a phone should
load, including scheme, the reachable address, port, and the token if
one is configured. The token is a random string that nobody should be
expected to transcribe from configuration, and the bind address is not
necessarily the address the phone must dial.

#### Scenario: The reachable URL is printed at startup
- **WHEN** the server starts bound to a network-reachable address with a
  token configured
- **THEN** it prints the full URL, carrying the token, that a phone
  should open
