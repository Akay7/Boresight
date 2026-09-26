## MODIFIED Requirements

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

## ADDED Requirements

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
