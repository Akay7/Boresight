## Why

The generated TLS certificate names the address the PC had the day it
was generated, and `resolve_certificate` reuses it for as long as the
files exist. When the PC's LAN address changes (DHCP lease, another
network, a laptop taken elsewhere), the server keeps serving a
certificate that does not cover the URL it prints, so the phone's
earlier acceptance is useless and the name mismatch is reported as a
generic certificate error. The same happens silently once the
certificate expires.

## What Changes

- On startup with a generated certificate, the persisted certificate is
  loaded and checked: its subjectAltName must cover the currently
  advertised host (IP or hostname), it must parse, and it must not be
  expired or within a renewal window of expiry.
- A certificate that fails the check is regenerated. The new one covers
  the current host and keeps the hosts the old one covered (bounded), so
  moving back and forth between known networks does not churn it.
- A regeneration is logged as a warning that says why, that phones must
  accept the certificate again, and that the SHA-256 fingerprint
  changed from the old value to the new one — an ESP32-CAM built with
  the old certificate must have it re-copied and be reflashed.
- A certificate that still covers the host and is in date keeps being
  reused unchanged, byte for byte.
- A user-supplied `--certfile`/`--keyfile` is never inspected or
  replaced.

## Capabilities

### New Capabilities

### Modified Capabilities
- `network-access`: the TLS requirement's reuse rule gains conditions —
  a generated certificate is reused only while it covers the advertised
  host and is in date, and is otherwise regenerated with a warning.

## Impact

- `src/boresight/netaccess.py`: `resolve_certificate`,
  `_write_self_signed`, new certificate-inspection helpers.
- `tests/test_network_access.py`: new tests.
- `README.md`: a note on when the certificate is regenerated.
- ESP32-CAM users: a regeneration requires re-copying the certificate
  into the firmware and reflashing; the warning says so.
