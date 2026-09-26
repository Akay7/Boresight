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

This change is that server visibility, plus the phone's `hello`. The
firmware itself was split out into `add-esp32-cam-firmware`, so this
side can be archived without waiting on hardware bring-up.

## What Changes

- Server: a `hello` control message labels a session with its client kind
  (logs and telemetry say "esp32-cam" rather than always "phone").
- Server: a new token-protected `GET /sessions` lists active frame
  sessions and their latest telemetry, so a camera without a screen can
  be observed from a browser or `curl`.
- Server: startup prints the connection details a headless client needs
  (address, port, frame path, token, and the certificate path and
  SHA-256 fingerprint when TLS is on), not only the phone URL.
- Phone client sends `hello` identifying itself as a phone.

## Capabilities

### New Capabilities
<!-- none: `esp32-cam-client` is in add-esp32-cam-firmware -->

### Modified Capabilities
- `video-ingest`: sessions can identify their client kind via a `hello`
  control message, and active sessions' telemetry becomes readable over
  HTTP for clients with no display of their own.
- `network-access`: startup output additionally reports the connection
  details and certificate fingerprint a headless client must be
  configured with.
- `phone-client`: the phone identifies itself when its connection opens.

## Impact

- Changed: `src/boresight/server.py` (hello handling, `/sessions`,
  startup output, client-neutral log wording), `src/boresight/stream.py`
  (session identity), `src/boresight/netaccess.py` (certificate
  fingerprint), `src/boresight/web/capture.js` (hello).
- Tests: new pytest coverage for hello, `/sessions` and startup output.
- Depends on `add-trigger-click` (the `trigger` control message and
  `triggers` telemetry count), which is implemented but not yet archived.
- The firmware that uses all of this is `add-esp32-cam-firmware`.
