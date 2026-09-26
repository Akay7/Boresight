## Context

Authentication is one middleware (`require_token` in `server.py`)
plus a separate check in the `/ws/frames` route, both reading the token
through `netaccess.presented_token` from `?token=` or
`Authorization: Bearer`. The query parameter existed because a browser
cannot set headers on a WebSocket handshake — but a browser *does*
send cookies on one, which removes the reason for the phone to put the
token in any URL after the first. Uvicorn formats every request target
with its query string (`get_path_with_query_string`) and logs it as a
`%s` argument: the access line on `uvicorn.access`, the WebSocket
`[accepted]`/rejection lines on `uvicorn.error`. The ESP32-CAM firmware
authenticates with the query parameter on the socket and holds no
cookies; it is out of scope and must keep working unchanged.

## Goals / Non-Goals

**Goals:**
- After the first page load, no request the phone makes carries the
  token in its URL, and the phone's address bar and history no longer
  show it.
- Whatever still carries `token=` in a URL (the first load, the device,
  a hand-typed curl) is redacted from uvicorn's logs.
- Cookie auth introduces no new cross-origin way to drive the cursor.

**Non-Goals:**
- Changing the token's lifetime, rotation, or how it is generated.
- Protecting the startup banner: printing the URL with the token to the
  operator's terminal is the intended hand-off.
- Changing the firmware or the device's configuration.
- Redacting the token from logs other than uvicorn's (the project's own
  `boresight` logger never logs it) or from a reverse proxy in front.

## Decisions

**Cookie session over a POST-and-exchange or a fragment-based token.**
Alternatives considered: (a) put the token in the URL fragment
(`#token=`), which browsers never send — but then the page's own
script and the socket still need a credential channel, and the first
request for the page itself would be unauthenticated; (b) have the
page POST the token to a login route — an extra round trip and a new
endpoint for the same result. A cookie set on the response to the very
first request (`/?token=…`) is invisible to the phone's page logic,
covers the script load, fetches, the marker-sheet link and the WS
handshake at once, and needs no new route.

**Cookie attributes.** Name `boresight_token`; `HttpOnly` (page script
never needs to read it, so an injected script can't either);
`SameSite=Strict` (never attached to a cross-site navigation or
subresource); `Path=/`; `Secure` exactly when `config.tls` — plain HTTP
is a supported path (`adb reverse` to `http://localhost`), and a Secure
cookie would silently never be stored there. `Max-Age` 30 days: a
`--token-auto` token dies with the process anyway, and a fixed
`--token` is meant to be long-lived; re-issuing on every valid query
token keeps it fresh. The cookie value is the token itself rather than
a derived session id — a server-side session table would buy nothing
on a single-user LAN tool, would be lost on restart, and would add
state to test.

**Precedence: query, then bearer, then cookie — first present wins.**
A URL the operator just opened must override a cookie from an earlier
run with a different `--token-auto` value; the alternative ("any
matching source wins") would also work but would let a request carry a
wrong explicit token alongside a right cookie and be served, which
blurs what was actually presented. A wrong query token is rejected even
if the cookie is right.

**Set the cookie only on a valid query token, and only when it differs
from what the browser sent.** The bearer header is for programmatic
clients that don't want cookies; issuing one to them is noise. Skipping
the `Set-Cookie` when the browser already holds the same value keeps
static responses clean.

**Origin check for cookie-only credentials.** Moving to an ambient
credential opens cross-site request forgery and cross-site WebSocket
hijacking. `SameSite=Strict` stops other *sites*, but "site" ignores
the port, so another service on the same host (e.g. a dev server on
:8080) would be same-site and its pages would get the cookie attached
to a `new WebSocket("wss://host:7331/ws/frames")` — which is not
subject to CORS at all. So when the cookie is the only credential and
the request carries an `Origin` header, its `host:port` must equal the
request's `Host` header. Browsers always send `Origin` on a WebSocket
handshake and on cross-origin or non-GET fetches; same-origin GETs and
top-level navigations may omit it, which is why absence is accepted.
The query and bearer paths are exempt: they aren't ambient, and the
device sends no `Origin`. Alternative considered: a fixed allow-list of
origins from `ServerConfig.advertised_host()` — rejected because the
phone may reach the server via an address that isn't the advertised
one (`localhost` over `adb reverse`, a hostname), and the `Host` header
is by definition the address the client used.

**Redaction as a `logging.Filter` on the `uvicorn.access` and
`uvicorn.error` loggers, installed in `main` before `uvicorn.run`.**
Uvicorn's `dictConfig` removes and replaces handlers but only ever
*adds* logger filters, so a filter installed before `uvicorn.run`
survives it; a logger-level filter applies to records those loggers
create directly, which is exactly where the request-target lines come
from. The filter rewrites `record.msg` and every string in
`record.args` (tuple or mapping), replacing the value of any `token=`
occurrence — up to the next `&`, whitespace, quote or end — with
`***`. Generic rather than matching the configured token: wrong tokens
are credential attempts too, and the filter then needs no access to
config. Exposed as `install_log_redaction()` (idempotent) so it is
testable without starting uvicorn. Alternatives considered: disabling
the access log (`access_log=False`) loses the only record of who
connected and doesn't cover the WebSocket lines on `uvicorn.error`; a
custom `log_config` would replace uvicorn's formatting wholesale for a
one-regex job.

**Marker sheet stops propagating the token.** `_with_token` and the
hidden form input existed only because the sheet's links would
otherwise 401; the request that rendered the sheet with a valid query
token also set the cookie, and a sheet reached from the phone page is
already cookie-authenticated, so plain links suffice. The helper
becomes a plain link builder and `_size_picker` loses its `request`
parameter.

**Phone page.** `capture.js` strips `token` from `location.search` with
`history.replaceState` (keeping any other parameters and the hash) as
its first action, `sameOriginUrl()` no longer appends the token, and
`index.html`'s bootstrap loads `capture.js` with a plain `src` (the
page's own response already set the cookie). The 1008 message now also
covers a stale cookie from a restarted server.

## Risks / Trade-offs

[A browser with cookies disabled (or a private mode that drops them)
can no longer use the page past the first request] → Accepted: every
current mobile browser stores first-party cookies by default, and the
failure is loud (401 / the 1008 message), not silent. Such a browser
could still be served if the query token were kept in URLs, but that
is exactly the leak this change removes.

[The first request still carries the token in its URL, so it reaches
the log formatter] → Redacted by the filter; that is what the filter
is for.

[A reverse proxy or other logger in front of the server may log the
first URL] → Out of scope (see Non-Goals); the README says so.

[Two Boresight servers on the same host but different ports share one
cookie jar entry, since cookies ignore ports] → The query token of the
most recently opened URL wins and replaces the cookie; switching back
requires reopening that server's URL. Acceptable for a single-operator
tool.

[The redaction regex could miss a token encoded unusually, e.g.
`TOKEN=` or `token%3D`] → Starlette reads the parameter case-sensitively
as `token`, so only `token=` authenticates; an encoded form is not a
working credential. Matching is case-insensitive anyway, at no cost.

## Migration Plan

Additive for clients: an old phone page still sends `?token=` and keeps
working (and now also receives a cookie). The ESP32 is untouched.
Rollback is reverting the change; cookies left in browsers are then
simply ignored.
