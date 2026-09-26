## Context

`resolve_certificate` (`src/boresight/netaccess.py`) returns a supplied
`--certfile`/`--keyfile` pair untouched, and otherwise reuses
`.boresight/server.crt` + `server.key` whenever both files exist,
generating them only when missing. `_write_self_signed` puts
`localhost`, `127.0.0.1` and the advertised host at generation time in
subjectAltName. `server.main` resolves the certificate after logging is
configured and then prints `certificate_fingerprint(certfile)` under
`sha256`, which the ESP32-CAM firmware compares against the certificate
it embedded at build time (`firmware/boresight-cam/README.md`, TLS).
See proposal.md for why reuse-while-present is not enough.

## Goals / Non-Goals

**Goals:**
- A generated certificate always covers the host in the printed URL and
  is in date.
- No regeneration when nothing relevant changed, so the phone's
  acceptance and the ESP32's pinned copy stay valid.
- A regeneration is impossible to miss in the startup output and says
  what the operator has to do.

**Non-Goals:**
- Inspecting or warning about a supplied certificate. The operator owns
  it; the task is explicit that it is never touched.
- Reusing the private key across regenerations. Both the browser's
  acceptance and the ESP32's pin are of the certificate, not the key,
  so keeping the key saves nothing observable.
- Detecting a key that does not match the certificate. That is a
  hand-edited `.boresight/`, not an address change.

## Decisions

**Coverage check against SANs only, typed.** The advertised host is
parsed with `ipaddress.ip_address`; an IP must appear as an `IPAddress`
SAN (compared as address objects, so `::1`/`0:0::1` spellings agree),
otherwise the host is a name and must appear as a `DNSName`,
case-insensitively. The CN is ignored: browsers ignore it for matching
too. No wildcard matching — this code never generates wildcards.

**Renewal window of 30 days** (`CERT_RENEW_BEFORE_DAYS`). Validity is
825 days, so this costs nothing and avoids a certificate that works at
startup and expires during a long-running session. Alternative
considered: regenerate only once expired — rejected, since the failure
would then appear mid-session with nobody watching the log.

**Remember previous hosts, bounded to 8** (`CERT_MAX_HOSTS`). On
regeneration the new SAN list is: the current host first, then the
hosts the old certificate covered (in their old order, which is
most-recent-first because the current host always leads), deduplicated,
truncated to 8, with `localhost` and `127.0.0.1` always added on top and
not counted. A laptop moving between home and office therefore
regenerates once per new network and then never again. The bound keeps
a certificate on a DHCP-churning network from growing without limit;
the oldest address falls off first. An expiry-driven regeneration keeps
the old hosts too. An unreadable certificate has no hosts to keep.
Alternative considered: include every current local interface address
in the SAN so the first move never regenerates — rejected: it does not
help a network the machine has never been on, which is the actual case.

**Warning via the `boresight` logger, fingerprints included.**
`resolve_certificate` logs at WARNING, multi-line, naming the reason
(`does not cover 192.168.1.30`, `expires on …`, `could not be read`),
the path, that phones must accept the certificate again, the old and
new SHA-256 fingerprints, and that an ESP32-CAM built with the old
certificate must have `server.crt` re-copied into
`main/server_cert.pem` and be reflashed. Logging is already configured
before `resolve_certificate` runs in `server.main`, so no server change
is needed; the `sha256` line printed afterwards then shows the new
value. Alternative considered: return a status object and print from
`server.main` — rejected to keep the change inside `netaccess.py` (other
workers are editing `server.py`) and because the function already owns
the decision.

**First-time generation is logged at INFO**, not WARNING: there is no
previous acceptance to invalidate.

**Unreadable certificate regenerates rather than raising.** A truncated
file from an interrupted write would otherwise block startup with a
parse traceback over a file the server itself owns.

**The existence check stays "both files".** A cert without its key (or
vice versa) is regenerated as before, without a fingerprint comparison
when the cert is missing.

## Risks / Trade-offs

- [A regeneration on a network change breaks a flashed ESP32 until it is
  reflashed] → Unavoidable with a pinned self-signed certificate; the
  warning says exactly what to do, and host memory makes it a once-per-
  network event. A DHCP reservation for the PC avoids it on the home
  network.
- [Clock skew makes a certificate look expired] → Only within the 30-day
  window; the result is one extra regeneration, never a refusal.
- [A certificate listing several past LAN addresses discloses them to
  anyone who connects] → They are private addresses of the same machine
  on networks it has joined; bounded to 8.

## Migration Plan

None. An existing `.boresight/server.crt` is checked on the next start
like any other; one that covers the current host is kept unchanged.
