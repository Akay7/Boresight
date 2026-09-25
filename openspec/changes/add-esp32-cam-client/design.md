## Context

The server already treats the frame socket as transport-neutral:
`stream.py` defines the wire format (8-byte LE float64 client ms + JPEG),
`server.py`'s `run_frame_session` decodes into the shared pipeline, and
`_handle_control` dispatches JSON text messages (`rtt`, `trigger`,
`debug`). Nothing in that path knows about browsers except the log
wording ("phone connected") and the `client="phone"` default argument.

Constraints the hardware imposes:

- **AI-Thinker ESP32-CAM**: classic ESP32 (dual core, no native USB),
  OV2640, 4 MB PSRAM, PCB antenna, 2.4 GHz Wi-Fi only. JPEG is encoded by
  the sensor itself, so no CPU-side encoding.
- **Free GPIOs are scarce.** The camera takes most pins; GPIO16 is PSRAM;
  GPIO1/3 are the serial console; GPIO0, 2, 12 and 15 are boot straps
  (GPIO12 high at boot selects 1.8 V flash and bricks the boot); GPIO4 is
  the high-power flash LED. With the SD slot unused, **GPIO13 and GPIO14
  are the safe button pins**. GPIO33 is the on-board red LED, active-low.
- **No screen.** Everything the phone page displays has to go somewhere
  else: an LED, the serial log, or the server.
- **TLS is optional on the server.** `--tls` exists because *browsers*
  require a secure context for the camera. A device has no such
  requirement, but the token still crosses the network.

## Goals / Non-Goals

**Goals:**
- Zero changes to frame decoding, the drop slot, the pipeline or cursor
  injection. A device frame is a phone frame.
- A trigger press reaches `backend.click()` with no more delay than one
  in-flight frame write.
- The device is diagnosable from another machine without a serial cable.

**Non-Goals:**
- Buttons beyond the trigger doing anything else (reload, right click,
  marker-source switching). The button table is built to take more
  actions, but each new action needs a server-side control message and a
  cursor-backend operation, which is a separate change.
- ESP32-S3 native USB HID, IMU bridging, recoil — README's other
  hardware path, unaffected.
- Server discovery (mDNS) and on-device provisioning (captive portal).
  Build-time configuration is enough to prove the path.
- Over-the-air updates.
- Boards other than AI-Thinker ESP32-CAM. The pin map is isolated so
  another board is a new map, not a rewrite.
- Camera intrinsic calibration or lens-distortion correction.

## Decisions

### Reuse `/ws/frames` and its wire format unchanged

The firmware packs frames exactly as `stream.pack_frame` does and
connects to the same path with `?token=`. Alternatives considered:

- *MJPEG HTTP stream pulled by the server* (the stock
  `CameraWebServer` example): would need the server to become a client,
  a second ingest path with its own drop policy, and a second trigger
  channel. Rejected: it duplicates `video-ingest` for no gain.
- *UDP datagrams*: lower overhead, but JPEG frames (20–60 KB) exceed a
  datagram and need fragmentation and reassembly; loss handling would
  have to be rebuilt. Revisit only if measured latency demands it,
  mirroring README's WebRTC stance.

The e2e guarantee "a fixture file is a wire payload" then covers the
device too.

### ESP-IDF, not Arduino

`firmware/boresight-cam/` is an ESP-IDF v5.x project using
`espressif/esp32-camera` and `espressif/esp_websocket_client` from the
component registry (`idf_component.yml`). Arduino-ESP32 3.x no longer
bundles a WebSocket client, and the third-party ones either lack TLS
trust-anchor configuration on ESP32 or pin by fingerprint only on
ESP8266. ESP-IDF gives `esp_websocket_client` with mbedTLS
certificate pinning, Kconfig for configuration, FreeRTOS tasks and a
`linux` host story. PlatformIO was considered; it wraps the same IDF but
adds a second build system for contributors to install.

### Configuration via Kconfig, secrets in untracked `sdkconfig`

`main/Kconfig.projbuild` declares SSID, password, server host, port,
token, TLS on/off, resolution, JPEG quality, frame-rate cap, exposure,
gain, and the trigger GPIO (default 13). `sdkconfig.defaults` is tracked
and contains no secrets; `sdkconfig` is gitignored. `idf.py menuconfig`
is the interface. The server certificate is embedded from
`main/server_cert.pem` (gitignored) with `target_add_binary_data`, only
when TLS is on. With TLS on and the file missing, CMake stops with a
message naming the file to copy; with TLS off the file is not needed at
all. An empty SSID or host is checked at boot (Kconfig cannot express
"required string") and reported as the configuration-error LED pattern.

### TLS: pin the server's own self-signed certificate

When TLS is on, the embedded PEM (copied from `.boresight/cert.pem`) is
the sole trust anchor given to `esp_websocket_client`. mbedTLS accepts a
self-signed end-entity certificate that exactly matches a trusted entry,
so no CA is needed, and a different certificate fails the handshake
before the URI (and its token) is sent. Hostname checking stays on: the
generated certificate already carries the advertised LAN IP in
`subjectAltName`. The server prints the SHA-256 fingerprint at startup
and the firmware logs the fingerprint of the certificate it embedded, so
a mismatch is spotted by comparing two lines.

Disabling verification was rejected outright (spec forbids it). Plain
`ws://` remains supported because a server run solely for the device
does not need `--tls`, and TLS costs roughly 40 KB of heap and a
multi-second handshake on a classic ESP32; the README states the
trade-off — the token is sniffable on the LAN without TLS.

### Capture loop: synchronous, newest frame, rate-capped

One FreeRTOS task: `esp_camera_fb_get()` → pack header → send → return
frame buffer → sleep to the rate cap. The camera is configured with
`fb_location = PSRAM`, `fb_count = 2`, `grab_mode =
CAMERA_GRAB_LATEST`, so the driver overwrites unread frames instead of
queueing them — the device-side equivalent of `FrameSlot`. The send
uses a timeout (default 200 ms). A frame whose first fragment cannot go
out in time is dropped and `skipped` is counted; one that fails after the
header is already on the wire leaves a message that can be neither
finished nor retracted, so the session is ended and the link reconnects.
Frames are sent holding a link mutex, so no text message (a trigger) can
land between a frame's fragments, which WebSocket forbids. Because the
loop never holds more than the frame it is sending, no backlog can form;
this replaces the phone's `bufferedAmount` check, which has no
equivalent in the client library.

The header is built into a separate 8-byte buffer and sent with the
frame in one WebSocket message using the client's fragmented-send API
(`esp_websocket_client_send_bin_partial` + `send_cont_msg` + `send_fin`)
rather than copying a 50 KB JPEG into a new buffer per frame. The
timestamp is `esp_timer_get_time() / 1000.0` as an IEEE-754 double,
shifted out byte by byte in little-endian order rather than `memcpy`'d,
so the host tests prove the exact bytes the board sends.

Default resolution is SVGA (800×600) at quality 12, capped at 20 fps —
a guess, exactly as the phone's `CONFIG` defaults were, to be replaced
by telemetry. HD (1280×720) matches the fixtures but OV2640 JPEG at HD
is expected to run near 10 fps.

### Buttons: GPIO interrupt → debouncer → dedicated task

A GPIO any-edge interrupt notifies a high-priority button task; the task
samples the pin and runs an integrating debouncer (state changes after
the pin reads stable for 10 ms, configurable). A debounced
released→pressed transition emits the button's action; release and hold
emit nothing. The debouncer and the frame-header packing live in a
platform-independent component (`components/boresight_proto`) with no
IDF includes, so they build and test on the host with plain CMake.

The trigger task calls `esp_websocket_client_send_text` directly. The
client serialises sends with an internal lock, so the worst case is
waiting for the in-flight frame write — which is why the frame send has
a timeout. A press while disconnected is dropped at the task (checked
with `esp_websocket_client_is_connected`). Polling the pin from the
capture loop was rejected: it would tie trigger latency to frame period.

Button pins are validated against a per-board reserved-pin table at
boot.

### Telemetry the device consumes

The firmware parses only three fields of the server's `stats` message
with `cJSON` (bundled in IDF): `client_ms` (for `rtt`), `outcome` (for
the LED), `triggers` (logged). It sends `rtt` at most once per second, like
`capture.js`. Everything else is left to the server's `/sessions`.

### Status LED patterns (GPIO33)

| State | Pattern |
| --- | --- |
| Joining Wi-Fi | slow blink (1 Hz) |
| Connecting to server | fast blink (4 Hz) |
| Config / auth / TLS error | triple flash, pause |
| Streaming, last frame solved | solid on |
| Streaming, last frame unsolved | brief flash every second |

"Solved" means the last `stats.outcome` reported a position. A
stats message older than 1 s counts as unsolved, so a stalled server does
not leave the LED solid.

### Reconnection and back-off

Wi-Fi reconnects on `WIFI_EVENT_STA_DISCONNECTED` with exponential
back-off 1 s → 30 s. The WebSocket client's built-in reconnect is
disabled in favour of explicit handling, because a refused token must
back off to 30 s and show the error pattern instead of retrying every
second like a network blip. The server refuses a bad token before
accepting the socket, which a client sees as an HTTP 403 handshake
response (confirmed against uvicorn with a stand-in client), not as a
1008 close; the firmware treats 401/403 at the handshake and a 1008
close alike. A certificate mismatch backs off the same way.

### Server: `hello` and `/sessions`

`SessionStats` gains `client_kind`, `client_version`, `frame_size`
(all `None` until `hello`), and `_handle_control` gains a `hello` branch
that validates types and ignores bad input, matching the existing `rtt`
and `debug` posture. The `client` log label in `run_frame_session`
becomes `"<kind> <address>"`, and "phone connected/disconnected" becomes
"client connected/disconnected".

A `SessionRegistry` on `app.state` holds live sessions: registered after
`accept()`, removed in the existing `finally`. `GET /sessions` returns
`{"sessions": [...]}` where each entry is the remote address, identity,
`connected_s` and `stats.as_message()` with the `debug` key removed.
It is an ordinary HTTP route, so the existing `require_token` middleware
already covers it. Alternatives: logging only (no remote visibility
without SSH), or pushing telemetry to the phone page (couples the two
clients and needs a phone anyway).

### Server: headless connection details

`server.py` gains `_device_details(config, certfile)` formatting host,
port, path, TLS and token; `netaccess` gains `certificate_fingerprint(certfile)` (SHA-256
of the DER, colon-separated hex). `main()` prints a second block after
the phone URL. The fingerprint is computed from whichever certificate is
served — generated or supplied.

## Risks / Trade-offs

- [Brown-outs on camera init or Wi-Fi TX bursts with weak USB supplies]
  → README requires a 5 V ≥ 1 A supply and a capacitor across the rails;
  the firmware logs the reset reason at boot so brown-out resets are
  visible rather than looking like random reboots.
- [Wi-Fi throughput caps resolution × rate; PCB antenna inside a shell
  loses range] → rate cap and skip counting make it measurable;
  `/sessions` shows round-trip time and drops; README notes the u.FL
  antenna option (requires moving a 0 Ω resistor).
- [OV2640 rolling shutter smears fast swings] → short pinned exposure is
  the mitigation already assumed in README; global-shutter is out of scope.
- [OV2640 manual exposure range may be too coarse for the dim-room case]
  → exposure and gain are Kconfig values; README records measured values
  once hardware exists.
- [A session inherits the server's remembered debug flag at connect, so
  the device can receive stats messages carrying kilobytes of debug
  geometry per frame] → the firmware discards any text message larger
  than its receive buffer instead of assembling it, and does not send
  `debug` itself (that would also flip the phone's remembered setting);
  LED and `rtt` then pause only while debug is on, which the serial log
  states.
- [Trigger latency bounded by one frame write, which can reach the send
  timeout on a bad link] → 200 ms default timeout, configurable;
  a follow-up could timestamp the trigger message to measure it.
- [mbedTLS IP-SAN hostname matching may not accept the IP-literal
  certificate on some IDF versions] → verify during bring-up; if it
  fails, set `skip_cert_common_name_check` — safe here because the
  embedded certificate is the only trust anchor, so pinning alone
  still refuses any other server. Documented in the design, not silent.
- [Certificate regeneration (deleting `.boresight/`) silently breaks the
  device] → the device shows the error pattern and logs the TLS failure;
  README says to re-copy the certificate and re-flash.
- [No hardware in CI] → host tests cover packing and debouncing; server
  behaviour is covered by pytest; the rest is a manual bring-up
  checklist in tasks.md, clearly marked as needing hardware.

## Migration Plan

Purely additive. The phone client keeps working unmodified apart from
sending `hello`, which older servers ignore (unknown control types are
already dropped). Rollback is removing the firmware directory and
reverting the server additions; no stored state changes.

## Open Questions

- Real exposure, gain, resolution and frame-rate defaults — to be set
  from telemetry on hardware, as with the phone's `CONFIG`.
- Whether OV2640 wide-angle lens variants distort enough at the frame
  edges to need calibration; affects only the (unbuilt) intrinsics
  milestone.
