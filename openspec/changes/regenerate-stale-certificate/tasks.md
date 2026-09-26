## 1. Certificate generation

- [x] 1.1 Make `_write_self_signed` take a list of hosts (current first) and a validity period, putting each host in subjectAltName as an IP or DNS name alongside `localhost`/`127.0.0.1`; verify the existing reuse and key-permission tests still pass

## 2. Staleness check and regeneration

- [x] 2.1 Add helpers that read a persisted certificate's covered hosts and expiry, and decide whether it is stale for the advertised host (uncovered, expired or within `CERT_RENEW_BEFORE_DAYS`, unreadable); verify with tests for an IP cert resolved for another IP, a hostname, an expiring cert and a garbage file
- [x] 2.2 Regenerate a stale certificate in `resolve_certificate`, carrying the old hosts over bounded by `CERT_MAX_HOSTS`, and log a warning naming the reason, that phones must re-accept, the old and new fingerprints, and ESP32-CAM re-pinning; verify with tests on the log record, on returning to a remembered address without regeneration, and on the bound
- [x] 2.3 Keep supplied `--certfile`/`--keyfile` untouched even when they would be stale; verify with a test using a supplied certificate for another address

## 3. Docs and checks

- [x] 3.1 Note in README when the generated certificate is regenerated and what that means for phones and the ESP32-CAM; verify by reading the TLS sections
- [x] 3.2 Run `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check` and `openspec validate regenerate-stale-certificate`; all pass
