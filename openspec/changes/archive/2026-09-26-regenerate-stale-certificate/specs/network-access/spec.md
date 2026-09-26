## MODIFIED Requirements

### Requirement: The server can serve over TLS
The server SHALL support serving over TLS with a supplied or generated
certificate. This is not optional polish: browsers expose camera capture
only in a secure context, and a LAN IP over plain HTTP is not one, so
without TLS the phone client cannot access the camera at all. Where a
certificate is generated rather than supplied, it SHALL be persisted and
reused across restarts, so the phone's acceptance of it survives — but
only while it is still usable for the address the server now
advertises. At startup a persisted generated certificate SHALL be
checked, and SHALL be regenerated when it cannot be read, when its
subject alternative names do not cover the advertised host (an IP
address or a hostname), or when it has expired or will expire within a
renewal window. A regenerated certificate SHALL cover the advertised
host and SHALL keep a bounded number of the hosts the previous one
covered, so moving between known networks does not replace it again.
A regeneration SHALL be reported as a warning stating why it happened,
that phones must accept the new certificate again, and that the
certificate's SHA-256 fingerprint changed — naming the old and new
values — so a device that pins the certificate (the ESP32-CAM) must be
given the new one. A supplied certificate SHALL never be inspected,
replaced or regenerated.

#### Scenario: A generated certificate is reused across restarts
- **WHEN** the server is started with TLS enabled and no certificate has
  been supplied, and started again with the same advertised host
- **THEN** it generates one, persists it, and reuses the same
  certificate on subsequent starts rather than generating a new one

#### Scenario: A certificate for a previous address is regenerated
- **WHEN** a generated certificate was persisted while the server
  advertised one address, and the server is started advertising a
  different address the certificate does not cover
- **THEN** it generates a new certificate covering the new address,
  replaces the persisted one, and logs a warning that phones must accept
  the certificate again and that the fingerprint changed from the old
  value to the new one, which a pinning device must be updated with

#### Scenario: Returning to a remembered address does not regenerate
- **WHEN** a certificate was regenerated for a new address after
  covering an earlier one, and the server is started advertising the
  earlier address again
- **THEN** the persisted certificate still covers it and is reused
  unchanged

#### Scenario: A hostname is covered by name
- **WHEN** the server advertises a hostname rather than an IP address
- **THEN** a generated certificate covers that hostname, and a persisted
  certificate that does not name it is regenerated

#### Scenario: An expiring certificate is regenerated
- **WHEN** the persisted generated certificate has expired or is within
  the renewal window of its expiry
- **THEN** it is regenerated with a warning, even though it covers the
  advertised host

#### Scenario: An unreadable certificate is regenerated
- **WHEN** the persisted certificate file cannot be parsed as a
  certificate
- **THEN** it is regenerated with a warning rather than failing startup

#### Scenario: A supplied certificate is used as given
- **WHEN** the server is started with a certificate and key supplied
- **THEN** it serves TLS using them and generates nothing, whatever
  address the certificate covers and whenever it expires
