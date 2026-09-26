## Why

The phone path works, but a phone is a borrowed, bulky, general-purpose
device strapped into a gun shell, and its trigger is a touchscreen button
rather than the shell's real microswitch. An ESP32-CAM (ESP32 + OV2640 +
Wi-Fi, a few dollars, with spare GPIOs for push buttons) fits inside the
shell, wires straight to the physical trigger, and needs no browser,
certificate interstitial or screen.

Split out of `add-esp32-cam-client`, which keeps the server and phone
side. That side is code-complete, while this one waits on an ESP-IDF
build and hardware bring-up. The device's trigger-hold behaviour, first
proposed in `add-trigger-hold`, moved here with the rest of the device's
requirements.

## What Changes

- New firmware project `firmware/boresight-cam/` for the AI-Thinker
  ESP32-CAM. It joins Wi-Fi, connects to the existing `/ws/frames`
  socket with the shared token, and streams frames in the exact existing
  wire format (8-byte LE float64 capture time in ms + JPEG).
- The camera sensor's exposure and gain are pinned to configured values,
  and resolution, JPEG quality and frame rate are configurable. The
  firmware sends the newest captured frame and never queues stale ones.
- Push buttons wired to GPIO (active-low, internal pull-up) are debounced
  in firmware. The trigger sends a trigger `down` on press and `up` on
  release, so holding it holds the button (see `add-trigger-hold`).
- The firmware identifies itself with `hello`, reports round-trip time
  (`rtt`), reconnects on its own after Wi-Fi or socket loss, and signals
  its state on the on-board LED, since it has no screen.
- Wi-Fi credentials, server address, token and the TLS certificate to
  trust are build-time configuration kept out of version control.
- README: hardware option, wiring, flashing and configuration guide.

## Capabilities

### New Capabilities
- `esp32-cam-client`: firmware that turns an ESP32-CAM into the barrel
  camera and physical trigger. Covers capture and exposure, streaming
  over the existing wire protocol, button debouncing and trigger
  press/release, reconnection, status indication, and configuration.

### Modified Capabilities
<!-- none: the server-side requirements the device relies on are in
     add-esp32-cam-client and add-trigger-hold -->

## Impact

- New: `firmware/boresight-cam/` (ESP-IDF project, C), with a host-side
  test build for its platform-independent logic. ESP-IDF and the
  `esp32-camera` / `esp_websocket_client` components are firmware-only
  dependencies; the Python package gains none.
- Depends on `add-esp32-cam-client` (`hello`, `GET /sessions`, headless
  connection details), `add-trigger-click` (the `trigger` message and
  `triggers` count) and `add-trigger-hold` (the `down`/`up` states).
- `.gitignore`: firmware build output, `sdkconfig`, and the embedded
  server certificate.
