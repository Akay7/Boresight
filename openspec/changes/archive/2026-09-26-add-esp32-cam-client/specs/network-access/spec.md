## ADDED Requirements

### Requirement: Startup reports what a headless client must be configured with
In addition to the phone URL, the server SHALL print at startup the
connection details a client without a browser has to be configured
with: the reachable address, the port, the frame socket path, whether
TLS is on, and the token if one is configured. When TLS is on, it SHALL
also print the path of the certificate in use and its SHA-256
fingerprint, so the certificate embedded in a device can be checked
against the one the server actually serves.

#### Scenario: Plain-text connection details are printed
- **WHEN** the server starts bound to a network-reachable address with a
  token and without TLS
- **THEN** it prints the address, port, frame socket path and token, and
  states that TLS is off

#### Scenario: The certificate fingerprint is printed under TLS
- **WHEN** the server starts with TLS enabled
- **THEN** it prints the certificate's path and SHA-256 fingerprint
  alongside the connection details

#### Scenario: The fingerprint is stable across restarts
- **WHEN** the server is restarted with TLS enabled and a generated
  certificate already persisted
- **THEN** the printed fingerprint is identical to the previous start's
