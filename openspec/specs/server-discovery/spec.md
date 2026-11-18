# server-discovery Specification

## Purpose
Lets a device on the same local network find the Boresight server
without being told its address, so a device keeps working when the PC's
address changes, without ever learning the token from the network.

## Requirements

### Requirement: The server announces itself on the local network
When bound to an address other networks' devices can reach, the server
SHALL announce itself over multicast DNS service discovery as a service
of type `_boresight._tcp` on the port it listens on, for as long as it
runs, and SHALL withdraw the announcement when it stops. A server bound
only to loopback SHALL NOT announce itself.

#### Scenario: A network-bound server can be discovered
- **WHEN** the server is started bound to 0.0.0.0 on port 7331
- **THEN** a multicast DNS query for `_boresight._tcp` on the local
  network finds it, with this machine's address and port 7331

#### Scenario: A loopback server is not announced
- **WHEN** the server is started bound to 127.0.0.1
- **THEN** it makes no announcement

#### Scenario: Stopping the server withdraws the announcement
- **WHEN** an announcing server shuts down
- **THEN** it withdraws its announcement before exiting

### Requirement: The announcement carries what a device needs, never the token
The announcement SHALL state the frame socket path and whether the
server is serving over TLS. It SHALL NOT carry the token, any part of
it, or anything derived from it.

#### Scenario: The announcement describes the frame socket
- **WHEN** the server announces itself with TLS off
- **THEN** the announcement states the frame socket path and that TLS
  is off

#### Scenario: The token is not announced
- **WHEN** the server announces itself with a token configured
- **THEN** nothing in the announcement contains the token

### Requirement: The announcement can be turned off
The server SHALL NOT announce itself when told not to, by command-line
flag or by its settings file, even when bound to a network address.

#### Scenario: Announcing is switched off
- **WHEN** the server is started bound to 0.0.0.0 with announcing turned
  off
- **THEN** a multicast DNS query for `_boresight._tcp` does not find it

### Requirement: A device without a server address finds the server
When its server address setting is empty, the ESP32-CAM SHALL look the
server up through the announcement before each connection attempt, SHALL
connect to the address and port the announcement gives, and SHALL log
which server it found. It SHALL still present its own configured token.
When no server is found it SHALL retry with its usual back-off, showing
the connecting pattern.

#### Scenario: A device with no address connects to the announced server
- **WHEN** a device with an empty server address and the right token
  starts on the same network as an announcing server
- **THEN** it connects to that server and streams, and its serial log
  names the address and port it found

#### Scenario: The device follows the server to a new address
- **WHEN** the PC running the server gets a new address and the server
  is restarted
- **THEN** the device finds the server at its new address and resumes
  streaming without being reconfigured

#### Scenario: No server is announced yet
- **WHEN** a device with an empty server address starts before any
  server is announced
- **THEN** it keeps looking with its usual back-off and connects once a
  server is announced

### Requirement: Discovery does not override a configured address
A device with a server address configured SHALL connect to that address
and port and SHALL NOT use the announcement.

#### Scenario: A configured address wins
- **WHEN** a device configured with server address 192.168.1.40 is on a
  network where another Boresight server is also announced
- **THEN** it connects only to 192.168.1.40

### Requirement: A TLS mismatch is reported, not worked around
When the announced server's TLS setting differs from the device's own,
the device SHALL NOT connect to it. It SHALL log the mismatch and show
the error pattern. It SHALL NOT fall back to plain text with a TLS
server, or to TLS without its trusted certificate.

#### Scenario: A plain-text device meets a TLS server
- **WHEN** a device built without TLS, with no server address, finds a
  server announcing TLS on
- **THEN** it does not connect, and its serial log says the server
  requires TLS
