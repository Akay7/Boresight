## Purpose

Turns an ESP32-CAM into the gun's barrel camera and physical trigger,
streaming to the same server and frame socket the phone client uses, with
no browser, screen or phone involved.

## ADDED Requirements

### Requirement: Frames are streamed in the existing wire format
The firmware SHALL connect to the server's existing frame socket and send
each captured frame as one binary message: an 8-byte little-endian
float64 capture time in milliseconds from the device's own monotonic
clock, followed by the frame as JPEG. A frame from the ESP32-CAM SHALL be
indistinguishable on the wire from a frame from the phone client, so the
server needs no client-specific frame handling.

#### Scenario: A device frame is accepted by the unmodified frame handling
- **WHEN** the firmware sends a captured frame in which enough mapped
  markers are visible
- **THEN** the server decodes and solves it through the same path as a
  phone frame, and the cursor moves to the solved position

#### Scenario: The frame header matches the server's codec byte for byte
- **WHEN** the firmware's frame packing is given a capture time and JPEG
  payload
- **THEN** the resulting bytes equal what the server's frame packing
  produces for the same capture time and payload

### Requirement: The device authenticates with the shared token
The firmware SHALL present the configured token when opening the frame
socket, and SHALL treat the server's refusal of that token -- whether
a rejected handshake or a policy-violation close -- as a configuration
error rather than a transient fault: it SHALL report it on its status
indicator and serial log, and SHALL NOT reconnect in a tight loop.

#### Scenario: A configured token is presented
- **WHEN** the firmware opens the frame socket to a server with a token
  configured
- **THEN** it presents the token and the connection is served

#### Scenario: A rejected token is reported, not hammered
- **WHEN** the server refuses the token, by rejecting the handshake or
  by closing the socket with a policy-violation status
- **THEN** the device indicates an authentication error and waits a
  back-off interval of at least several seconds before trying again

### Requirement: The device can connect over TLS and verifies the server
When configured for TLS, the firmware SHALL connect over TLS and SHALL
verify the server against a certificate provided in its configuration,
refusing to stream to a server that presents a different certificate.
When not configured for TLS it SHALL connect in plain text. It SHALL NOT
connect over TLS with verification disabled, since that sends the token
to whoever answers.

#### Scenario: The expected certificate is accepted
- **WHEN** TLS is configured and the server presents the configured
  certificate
- **THEN** the connection is established and frames are streamed

#### Scenario: An unexpected certificate is refused
- **WHEN** TLS is configured and the server presents a different
  certificate
- **THEN** the device does not send the token or any frame, and
  indicates a connection error

### Requirement: Exposure is pinned to configured values
The firmware SHALL disable the sensor's automatic exposure and automatic
gain and apply configured fixed values before streaming, and SHALL log
the exposure, gain, resolution and JPEG quality actually applied. Paper
markers beside a bright panel are a severe dynamic-range case and
auto-exposure chases the panel.

#### Scenario: Fixed exposure is applied at startup
- **WHEN** the device initialises the camera
- **THEN** automatic exposure and gain are off, the configured values are
  applied, and the applied settings are written to the serial log

### Requirement: Stale frames are never queued
The firmware SHALL send the most recently captured frame and SHALL NOT
accumulate a backlog of captured frames waiting to be sent. When a send
cannot complete within the configured timeout, the firmware SHALL skip
that frame, count the skip, and capture a fresh one rather than retry
the stale frame.

#### Scenario: A slow link skips frames instead of lagging
- **WHEN** the network cannot carry frames at the configured capture rate
- **THEN** the server keeps receiving recent frames, the device's skipped
  count increases, and the delay between capture and send does not grow
  over the session

#### Scenario: The capture rate is capped
- **WHEN** the link and server are faster than the configured frame rate
- **THEN** the device sends no more frames per second than configured

### Requirement: Buttons are configurable
The firmware SHALL let each connected push button be configured with its
GPIO and the action it performs, SHALL wire buttons active-low using the
chip's internal pull-up so a button needs only two wires to ground, and
SHALL reject at startup a configuration that assigns a button to a GPIO
the board uses for the camera, PSRAM, serial console, or a boot-strapping
function.

#### Scenario: A button on a free GPIO is accepted
- **WHEN** the trigger is configured on a GPIO the board leaves free
- **THEN** the device starts and the button works with no external
  resistor

#### Scenario: A button on a reserved GPIO is refused
- **WHEN** a button is configured on a GPIO the camera or boot
  strapping uses
- **THEN** the device reports the invalid pin on its serial log and
  status indicator and does not start streaming

### Requirement: The device reports round-trip time and identifies itself
The firmware SHALL send a `hello` message identifying itself as an
ESP32-CAM, with its firmware version and capture resolution, when each
connection opens. It SHALL compute round-trip time from the capture
timestamp the server echoes in telemetry against its own clock and SHALL
report it with the existing `rtt` control message at least once a
second while streaming.

#### Scenario: The device identifies itself on connect
- **WHEN** the firmware's frame socket connection opens
- **THEN** its first message is a `hello` naming the client kind, the
  firmware version and the capture resolution

#### Scenario: Round-trip time reaches the server
- **WHEN** the device has streamed frames and received telemetry for at
  least one second
- **THEN** the server's telemetry for that session carries a round-trip
  time measured by the device

### Requirement: The device recovers from connection loss on its own
The firmware SHALL reconnect to Wi-Fi and to the frame socket
automatically after either is lost, with a bounded back-off, and SHALL
resume streaming without a reset or any user action. It SHALL stop
sending frames while disconnected.

#### Scenario: The server restarts mid-session
- **WHEN** the server is stopped and started again while the device is
  streaming
- **THEN** the device reconnects and resumes streaming once the server is
  reachable, without being power-cycled

#### Scenario: Wi-Fi drops and returns
- **WHEN** the access point becomes unreachable and later returns
- **THEN** the device rejoins the network and resumes streaming

### Requirement: Device state is visible without a screen
The firmware SHALL indicate on the board's status LED, with
distinguishable patterns, at least: joining Wi-Fi, connecting to the
server, a configuration or authentication error, streaming with the most
recent reported frame solved, and streaming with the most recent
reported frame unsolved. The person holding the gun has no screen, and
"is it seeing the markers" is the question they need answered. The
firmware SHALL NOT use the board's high-power flash LED for status.

#### Scenario: Losing the markers changes the indication
- **WHEN** the device is streaming and the server's telemetry changes
  from a solved frame to an unsolved one
- **THEN** the status LED switches from the solved pattern to the
  unsolved pattern

#### Scenario: An authentication failure is distinguishable
- **WHEN** the server rejects the device's token
- **THEN** the status LED shows the error pattern rather than the
  connecting pattern

### Requirement: Secrets are configured outside version control
Wi-Fi credentials, the server address, the token and the trusted
certificate SHALL be supplied as build-time configuration that is
excluded from version control, and the firmware project SHALL ship
defaults containing no secrets. A firmware built without the required
Wi-Fi and server settings SHALL fail at build time or report the
missing setting at boot, rather than silently fail to connect.

#### Scenario: A fresh checkout contains no credentials
- **WHEN** the repository is cloned
- **THEN** no Wi-Fi password, token or server certificate is present in
  the firmware project's tracked files

#### Scenario: Missing configuration is reported
- **WHEN** the firmware is built or booted without a Wi-Fi SSID or server
  address configured
- **THEN** the build fails or the device reports the missing setting on
  its serial log and status indicator

### Requirement: The trigger button is held while it is pressed
The firmware SHALL send one trigger `down` message when the debounced
trigger button goes down and one trigger `up` message when it comes back
up, so holding the button holds the primary button and contact bounce
produces neither extra presses nor extra releases. A press while the
socket is not connected SHALL be discarded rather than delivered later.
An `up` SHALL be sent only for a `down` that was delivered on the
connection that is still open; a release after the connection dropped
SHALL send nothing, since the server already released the hold when the
session ended.

#### Scenario: A trigger is not held back by frame streaming
- **WHEN** the trigger is pressed or released while frames are streaming
- **THEN** its message is sent no later than after the frame send
  already in progress, not after further queued frames

#### Scenario: Press and release send down and up
- **WHEN** the connected device's trigger button is pressed, held for a
  second, and released, with contact bounce on both edges
- **THEN** exactly one `down` and then one `up` are sent

#### Scenario: A press while disconnected is not replayed
- **WHEN** the trigger button is pressed while the socket is down, the
  connection is re-established, and the button is then released
- **THEN** neither `down` nor `up` is sent for that press

#### Scenario: A hold broken by a reconnect sends no stray release
- **WHEN** the button is pressed while connected, the connection drops
  and is re-established, and the button is then released
- **THEN** no `up` is sent on the new connection
