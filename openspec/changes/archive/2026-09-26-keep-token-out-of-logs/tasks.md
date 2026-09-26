## 1. Credential sources (netaccess)

- [x] 1.1 Add `TOKEN_COOKIE_NAME` and a cookie lifetime constant, and
      extend `presented_token` with a cookie source ranked after the
      query parameter and bearer header; verify with the updated
      precedence unit test in `tests/test_network_access.py`
- [x] 1.2 Add an origin check (`Origin` host:port must equal `Host`
      when present) for cookie-only credentials; verify with unit tests
      covering absent, matching and foreign origins
- [x] 1.3 Add a `token=` redacting `logging.Filter` and an idempotent
      `install_log_redaction()` for `uvicorn.access` and
      `uvicorn.error`; verify with tests redacting both message and
      args (tuple and mapping) forms, wrong tokens included

## 2. Server

- [x] 2.1 In `require_token`, accept the cookie (with the origin check)
      and set the cookie (HttpOnly, SameSite=Strict, Path=/, Max-Age,
      Secure iff TLS) on a valid query token; verify with tests for
      cookie set / not set, cookie-only access, wrong cookie 401,
      foreign-origin 401, and the attributes under TLS and plain config
- [x] 2.2 Make `/ws/frames` accept the bearer header and the cookie
      (with the origin check) besides the query parameter; verify with
      WebSocket tests for cookie-only accept, wrong cookie 1008 and
      foreign-origin 1008, and the existing query-param test still
      passing
- [x] 2.3 Call `install_log_redaction()` in `main` before
      `uvicorn.run`; verify by starting the server locally and checking
      a request's access line shows `token=***` (done against a live
      uvicorn on loopback: `GET /?token=*** ... 200`, the wrong-token
      `401`, and `"WebSocket /ws/frames?token=***" [accepted]` / `403`
      all redacted; a cookie-only handshake logged as
      `"WebSocket /ws/frames" [accepted]`)

## 3. Clients

- [x] 3.1 `capture.js`: strip `token` from the address bar with
      `history.replaceState`, stop appending it in `sameOriginUrl()`,
      reword the 1008 message; verify with `node --check` and the
      script-content test
- [x] 3.2 `index.html`: load `capture.js` with a plain `src` and update
      the comments; verify with the rewritten
      "loads its own script" test (page references `capture.js` without
      a token, and the script is reachable with the cookie alone)
- [x] 3.3 `markers.py`: drop token propagation from links and the size
      picker form; verify with the rewritten marker-route test (no
      token in the sheet, the layout link reachable by cookie)

## 4. Docs and checks

- [x] 4.1 Update README's description of how the token travels
- [x] 4.2 Run `uv run pytest -q`, `uv run ruff check .` and
      `uv run ruff format --check .`; all pass
