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

## Scope

This change is the server and phone side of the ESP32-CAM client:
session identity via `hello`, `GET /sessions`, and the connection
details printed at startup. The firmware itself, with its requirements,
design and hardware bring-up, is `add-esp32-cam-firmware`.

## Decisions

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

## Migration Plan

Purely additive. The phone keeps working unmodified apart from sending
`hello`, which older servers ignore (unknown control types are already
dropped). Rollback is reverting the server additions; no stored state
changes.
