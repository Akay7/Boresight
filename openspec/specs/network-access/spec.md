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
valid token. A client SHALL be able to present the token as a query
parameter, as a bearer authorization header, or as the session cookie
the server issues; the query parameter and header SHALL keep working
for clients that hold no cookies, such as an embedded camera device.
Where a request presents the token in more than one way, the query
parameter SHALL take precedence, then the header, then the cookie, so a
freshly opened URL overrides a stale cookie rather than being masked by
it. Tokens SHALL be compared in a way that does not leak their contents
through timing.

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

#### Scenario: The session cookie alone authorizes a request
- **WHEN** a token is configured and a client presents only a session
  cookie carrying the valid token, on an HTTP request or on the frame
  socket handshake
- **THEN** the request is served, and the socket is accepted

#### Scenario: A wrong cookie is rejected like a wrong token
- **WHEN** a token is configured and a client presents only a session
  cookie carrying a wrong value
- **THEN** an HTTP request is refused as unauthorized and the frame
  socket is closed with a policy-violation status

#### Scenario: A cookie-less device keeps using the query parameter
- **WHEN** a token is configured and a client that sends no cookies
  opens the frame socket with the token as a query parameter
- **THEN** the socket is accepted exactly as before

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

### Requirement: A token presented in the URL is exchanged for a session cookie
When an HTTP request presents a valid token as a query parameter, the
server SHALL set a session cookie carrying the token, so that a browser
needs the token in a URL only once. The cookie SHALL be unreadable by
page script, SHALL NOT be sent on cross-site requests, SHALL be scoped
to the whole server, SHALL expire after a bounded lifetime, and SHALL
be restricted to secure connections whenever the server is serving TLS.
No cookie SHALL be set in response to an invalid token.

#### Scenario: A valid query token sets the cookie
- **WHEN** a token is configured and a browser requests a page with the
  valid token as a query parameter
- **THEN** the response sets the session cookie, marked HttpOnly,
  SameSite=Strict, scoped to path `/`, with a finite lifetime

#### Scenario: An invalid query token sets nothing
- **WHEN** a token is configured and a request carries a wrong token as
  a query parameter
- **THEN** the request is refused and no session cookie is set

#### Scenario: The cookie is secure-only under TLS
- **WHEN** the server is configured to serve TLS and issues the cookie
- **THEN** the cookie is marked Secure; when the server is not serving
  TLS it is not, so a phone reaching it as plain-HTTP localhost still
  receives it

### Requirement: A cookie is honoured only from the server's own pages
Where a request's only credential is the session cookie, the server
SHALL refuse it if it carries an `Origin` that is not the server's own
address. Browsers attach a cookie to requests other pages make, and
SameSite does not distinguish two services on the same host; a
credential carried in a URL or header is not ambient, so this check
applies to the cookie alone.

#### Scenario: A foreign page cannot ride the cookie
- **WHEN** a request carrying only a valid session cookie arrives with
  an `Origin` naming a different host or port than the server's own
- **THEN** an HTTP request is refused as unauthorized and the frame
  socket is closed with a policy-violation status

#### Scenario: The server's own page is served
- **WHEN** a request carrying only a valid session cookie arrives with
  no `Origin`, or with the server's own origin
- **THEN** it is served normally

### Requirement: The token's value is kept out of server logs
The server SHALL NOT write a token's value to its request or connection
logs. Any `token=` value appearing in a logged request target SHALL be
replaced with a fixed placeholder before the record is emitted,
whether or not the value was the correct token, since a near-miss is
often one character from the real one and a wrong token logged is still
a credential attempt worth not recording. The startup message that
prints the phone URL with the token is exempt: it is the one intended
disclosure, to the operator at the console.

#### Scenario: A request carrying the token is logged without it
- **WHEN** a client requests any endpoint with `?token=<value>` and the
  server logs the request
- **THEN** the log line shows `token=***` in place of the value

#### Scenario: A socket handshake carrying the token is logged without it
- **WHEN** a client opens the frame socket with `?token=<value>` and
  the server logs the handshake
- **THEN** the log line shows `token=***` in place of the value

#### Scenario: A wrong token is redacted too
- **WHEN** a request carries a token value that is not the configured
  token and the server logs it
- **THEN** that value is likewise replaced with the placeholder
