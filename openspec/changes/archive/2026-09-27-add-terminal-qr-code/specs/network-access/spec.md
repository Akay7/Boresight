## ADDED Requirements

### Requirement: Startup shows the phone URL as a scannable code
When the server prints the URL a phone should open, it SHALL also print
that same URL, token included, as a QR code drawn in the terminal, so
the phone can scan it instead of the operator typing it. The code SHALL
be printed only when standard output is an interactive terminal large
enough to show it whole and able to display it; otherwise it SHALL be
omitted without error and the URL line printed alone. A command-line
flag SHALL disable the code. The code SHALL be written directly to the
console, as the URL line is, and never to a logger.

#### Scenario: A code is printed in an interactive terminal
- **WHEN** the server starts with standard output on a terminal large
  enough for the code
- **THEN** it prints the URL line and a QR code that decodes to exactly
  that URL

#### Scenario: Redirected output carries no code
- **WHEN** the server starts with standard output redirected to a file
  or pipe
- **THEN** it prints the URL line and no QR code

#### Scenario: A terminal too small for the code
- **WHEN** the terminal is narrower or shorter than the code
- **THEN** no code is printed and the URL line still is

#### Scenario: The code can be turned off
- **WHEN** the server is started with `--no-qr`
- **THEN** no code is printed and the URL line still is

#### Scenario: The code never reaches the logs
- **WHEN** the server starts and prints the code
- **THEN** no log record contains the code or the token it encodes

## MODIFIED Requirements

### Requirement: The token's value is kept out of server logs
The server SHALL NOT write a token's value to its request or connection
logs. Any `token=` value appearing in a logged request target SHALL be
replaced with a fixed placeholder before the record is emitted,
whether or not the value was the correct token, since a near-miss is
often one character from the real one and a wrong token logged is still
a credential attempt worth not recording. The startup message that
prints the phone URL with the token, and the QR code of that URL, are
exempt: they are the one intended disclosure, to the operator at the
console, and are printed to the console rather than logged.

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
