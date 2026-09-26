## Why

Joining the phone means typing a URL like
`https://192.168.1.20:7331/?token=3q2-Xb0_...` from the terminal into a
phone keyboard. The token is 22 random characters that are deliberately
unguessable, which also makes them miserable to transcribe, and one
wrong character only produces a 403. The phone already has a camera
pointed at the screen; it can read the URL itself.

## What Changes

- At startup, next to the existing "Open this on the phone" line, the
  server prints a QR code of that same URL, token included, drawn with
  half-block characters so it fits in a normal terminal.
- The code is printed only where it can actually be scanned: stdout must
  be an interactive terminal, wide and tall enough for the code, and
  able to encode the block characters. Otherwise it is silently left
  out and the URL line alone is printed, exactly as today.
- A new `--no-qr` flag turns it off, e.g. when the terminal is being
  screen-shared or recorded.
- The QR is written to the console directly, like the URL line, and
  never through a logger; the log-redaction rules are unchanged.
- Adds `segno` (pure Python, no dependencies) as a runtime dependency.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities
- `network-access`: startup additionally shows the phone URL as a
  scannable code in an interactive terminal, with a flag to disable it;
  the token-in-logs requirement names the code as part of the one
  intended console disclosure.

## Impact

- `src/boresight/terminal_qr.py` (new): encode and render the code.
- `src/boresight/server.py`: `--no-qr` flag and one call in `main()`
  after the URL line.
- `pyproject.toml` / `uv.lock`: `segno` dependency.
- README: one short note.
- No change to the HTTP API, the phone client or the ESP32 firmware.
