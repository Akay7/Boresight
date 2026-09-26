## Why

The shared token is the only thing standing between the Wi-Fi and the
operator's mouse, yet it is written to disk on every request. The phone
page carries `?token=` on every fetch and on the frame socket URL, and
uvicorn logs the full request target — the access log for HTTP
(`uvicorn.access`) and the handshake line for WebSockets
(`"WebSocket /ws/frames?token=..." [accepted]` on `uvicorn.error`). So
anyone with read access to the server's console output, a redirected
log file, or a journal gets a credential that moves the operator's
cursor. The marker sheet compounds it by copying the token into its
links and a hidden form field, and the phone's address bar keeps it in
browser history.

## What Changes

- The server exchanges a valid query-parameter token for a session
  cookie (HttpOnly, SameSite=Strict, `Secure` when serving TLS), and
  accepts that cookie as a third credential source alongside the query
  parameter and the bearer header — on HTTP and on the frame socket.
- A request authenticated only by the cookie is refused when it carries
  an `Origin` that is not the server's own, so the ambient credential
  cannot be ridden by another page on the same host.
- The phone page removes the token from its address bar once loaded and
  stops putting it on fetch and WebSocket URLs; the cookie carries it.
  The page's bootstrap loads its script with a plain `src`.
- The marker sheet stops copying the token into its links and form; the
  cookie set when the sheet was opened carries it.
- As defence in depth, uvicorn's access and error loggers redact the
  value of any `token=` occurrence (valid or not) before a record is
  emitted.
- Unchanged: the query parameter and bearer header keep working for
  cookie-less clients (the ESP32-CAM firmware is untouched), and the
  startup banner still prints the phone URL with the token — the one
  intended disclosure, to the operator.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `network-access`: the token requirement gains a cookie credential
  (issued on a valid query token, same-origin only), and a new
  requirement keeps the token's value out of server logs.
- `phone-client`: the page stops carrying the token in its address bar
  and request URLs, relying on the session cookie instead.

## Impact

- Changed code: `src/boresight/netaccess.py` (cookie constants, cookie
  as a credential source, origin check, log redaction filter),
  `src/boresight/server.py` (middleware issues/accepts the cookie, the
  frame socket accepts it, `main` installs redaction),
  `src/boresight/markers.py` (no token propagation),
  `src/boresight/web/index.html` and `web/capture.js` (no token in URLs,
  address bar cleaned), `README.md` (how the token travels).
- Tests: `tests/test_network_access.py` (new cases, one rewritten),
  `tests/test_marker_routes.py` (token-propagation test rewritten).
- No new dependencies, no wire-format change for the frame socket, no
  firmware change.
