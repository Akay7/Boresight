## Why

The phone path works, but a phone is a borrowed, bulky, general-purpose
device strapped into a gun shell, and its trigger is a touchscreen button
rather than the shell's real microswitch. An ESP32-CAM (ESP32 + OV2640 +
Wi-Fi, a few dollars, with spare GPIOs for push buttons) fits inside the
shell, wires straight to the physical trigger, and needs no browser,
certificate interstitial or screen. The server side was built for this:
the frame socket's wire format is transport-neutral and the trigger
already rides its text channel, so a second kind of client costs firmware
plus a little server visibility, not a new pipeline.

## What Changes

- New firmware project `firmware/boresight-cam/` for the AI-Thinker
  ESP32-CAM that joins Wi-Fi, connects to the existing `/ws/frames`
  socket with the shared token, and streams frames in the exact existing
  wire format (8-byte LE float64 capture time in ms + JPEG) — the server's
  frame handling and the aim pipeline are unchanged.
- The camera sensor's exposure and gain are pinned to configured values,
  and resolution, JPEG quality and frame rate are configurable; the
  firmware sends the newest captured frame and never queues stale ones.
- Push buttons wired to GPIO (active-low, internal pull-up) are debounced
  in firmware; the trigger button sends the existing
  `{"type": "trigger"}` message on each press, never on release or hold.
- The firmware reports round-trip time back (`rtt`), identifies itself
  with a `hello` message, reconnects on its own after Wi-Fi or socket
  loss, and signals its state on the on-board LED, since it has no
  screen.
- Wi-Fi credentials, server address, token and the TLS certificate to
  trust are build-time configuration kept out of version control.
- Server: a `hello` control message labels a session with its client kind
  (logs and telemetry say "esp32-cam" rather than always "phone").
- Server: a new token-protected `GET /sessions` lists active frame
  sessions and their latest telemetry, so a camera without a screen can
  be observed from a browser or `curl`.
- Server: startup prints the connection details a headless client needs
  (address, port, frame path, token, and the certificate path and
  SHA-256 fingerprint when TLS is on), not only the phone URL.
- Phone client sends `hello` identifying itself as a phone.
- README: hardware option, wiring, flashing and configuration guide.

## Capabilities

### New Capabilities
- `esp32-cam-client`: firmware that turns an ESP32-CAM into the barrel
  camera and physical trigger — capture and exposure, streaming over the
  existing wire protocol, button debouncing and trigger events,
  reconnection, status indication, and configuration.

### Modified Capabilities
- `video-ingest`: sessions can identify their client kind via a `hello`
  control message, and active sessions' telemetry becomes readable over
  HTTP for clients with no display of their own.
- `network-access`: startup output additionally reports the connection
  details and certificate fingerprint a headless client must be
  configured with.
- `phone-client`: the phone identifies itself when its connection opens.

## Impact

- New: `firmware/boresight-cam/` (ESP-IDF project, C), with a host-side
  test build for its platform-independent logic. Adds ESP-IDF and the
  `esp32-camera` / `esp_websocket_client` components as firmware-only
  dependencies; the Python package gains none.
- Changed: `src/boresight/server.py` (hello handling, `/sessions`,
  startup output, client-neutral log wording), `src/boresight/stream.py`
  (session identity), `src/boresight/netaccess.py` (certificate
  fingerprint), `src/boresight/web/capture.js` (hello).
- Tests: new pytest coverage for hello, `/sessions` and startup output;
  firmware host tests for frame packing and debouncing.
- Depends on `add-trigger-click` (the `trigger` control message and
  `triggers` telemetry count), which is implemented but not yet archived.
- `.gitignore`: firmware build output, `sdkconfig`, and the embedded
  server certificate.
