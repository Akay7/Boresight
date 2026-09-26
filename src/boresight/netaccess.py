"""Reaching the server from another device, safely.

The phone is a separate machine and cannot reach loopback, so serving it
means binding an address the LAN can route to. That is the moment this
project acquires a real attack surface: an endpoint that moves the
operator's mouse, reachable by anything that joins the Wi-Fi, with no
local symptom whatsoever.

So the rule here is blunt. Loopback stays the default, a token is
required to bind anything else, and the process refuses to start rather
than warn. The convenience being denied -- running an open cursor-mover
on a network -- is one nobody has a reason to want.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import logging
import re
import secrets
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7331
DEFAULT_CERT_DIR = Path(".boresight")
CERT_NAME = "server.crt"
KEY_NAME = "server.key"
CERT_VALID_DAYS = 825
# Renew this long before expiry rather than at it, so a certificate that
# works at startup does not expire partway through a session.
CERT_RENEW_BEFORE_DAYS = 30
# Addresses a generated certificate keeps covering, current one first.
# Earlier ones are kept so moving between known networks does not
# replace the certificate each time; bounded so a DHCP-churning network
# cannot grow it forever. `localhost` and 127.0.0.1 come on top.
CERT_MAX_HOSTS = 8
_ALWAYS_COVERED = ("localhost", "127.0.0.1")

logger = logging.getLogger("boresight")

TOKEN_QUERY_PARAM = "token"

# The browser keeps the token here after the first request that carried
# it in the URL, so nothing after that has to. A URL is copied into
# access logs, browser history and screenshots; a cookie is not.
TOKEN_COOKIE_NAME = "boresight_token"
# Long enough not to nag on a fixed `--token`; a `--token-auto` token
# dies with the process regardless, and every valid URL re-issues it.
TOKEN_COOKIE_MAX_AGE_S = 30 * 24 * 3600

# The loggers uvicorn writes request targets to, query string included:
# the access line for HTTP, and the handshake line for WebSockets.
UVICORN_REQUEST_LOGGERS = ("uvicorn.access", "uvicorn.error")
REDACTED = "***"


class InsecureConfigurationError(RuntimeError):
    """Raised for a configuration that would expose an open server."""


def is_loopback(host: str) -> bool:
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        # A hostname we cannot classify. Treat it as reachable: the
        # safe direction to be wrong in is "demand a token".
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(16)


@dataclass
class ServerConfig:
    """How the server listens, and to whom.

    `token=None` means no authentication, which is only permitted on
    loopback. `validate()` enforces that and is called before anything
    binds.
    """

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    token: str | None = None
    tls: bool = False
    certfile: Path | None = None
    keyfile: Path | None = None
    cert_dir: Path = DEFAULT_CERT_DIR

    def validate(self) -> None:
        if not is_loopback(self.host) and not self.token:
            raise InsecureConfigurationError(
                f"refusing to bind {self.host}: a token is required to serve a "
                "network-reachable address. Anything on the network could "
                "otherwise move your cursor. Pass --token, or --token-auto to "
                "generate one, or bind 127.0.0.1."
            )

    @property
    def scheme(self) -> str:
        return "https" if self.tls else "http"

    def advertised_host(self) -> str:
        """The address a phone should dial.

        `0.0.0.0` means "every interface", which is not something a
        phone can connect to, so resolve it to this machine's actual LAN
        address.
        """
        if self.host not in ("0.0.0.0", "::"):
            return self.host
        return _primary_lan_address()

    def phone_url(self) -> str:
        """The complete URL to open on the phone, token included.

        The token is random and nobody should be asked to transcribe it
        from a config file, so it is printed ready to use.
        """
        url = f"{self.scheme}://{self.advertised_host()}:{self.port}/"
        if self.token:
            url += f"?{TOKEN_QUERY_PARAM}={self.token}"
        return url


def _primary_lan_address() -> str:
    """This machine's address on the route out, without sending anything.

    Connecting a UDP socket only sets the kernel's destination; no
    packet leaves. It is the standard way to ask "which local address
    would be used to reach the outside world".
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 1))  # TEST-NET-1, never routed
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def token_matches(configured: str | None, presented: str | None) -> bool:
    """Constant-time token comparison.

    `compare_digest` rather than `==` so a wrong token cannot be
    narrowed down by timing how long the rejection took.
    """
    if not configured:
        return True
    if not presented:
        return False
    return secrets.compare_digest(configured, presented)


def presented_token(
    query_token: str | None,
    authorization: str | None,
    cookie_token: str | None = None,
) -> str | None:
    """Pull the token from whichever place the client put it.

    A browser cannot set headers on a WebSocket handshake, but it does
    send cookies on one -- so after its first request the phone uses the
    cookie the server issued, and the query parameter remains for
    clients that hold no cookies (the ESP32) and for that first request.
    Everything else may use a bearer header.

    First present wins, query first: the URL the operator just opened
    must override a cookie left by an earlier run with a different
    `--token-auto` value, not be masked by it.
    """
    if query_token:
        return query_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[len("bearer ") :].strip()
    if cookie_token:
        return cookie_token
    return None


def origin_matches_host(origin: str | None, host: str | None) -> bool:
    """Whether a request's `Origin` is this server's own address.

    Checked only when the cookie is the sole credential. A cookie is
    ambient: the browser attaches it to requests other pages make, and
    SameSite ignores the port, so another service on the same host
    counts as same-site. A WebSocket handshake is not subject to CORS
    either, so without this a page served from :8080 could open the
    frame socket on :7331 and drive the cursor. Browsers always send
    `Origin` on a handshake and on cross-origin requests; a same-origin
    GET or a navigation may omit it, hence absent is fine.

    Compared against `Host` rather than the advertised address, because
    `Host` is by definition the address this client used -- which may
    be `localhost` over `adb reverse`, not the LAN IP.
    """
    if not origin:
        return True
    if not host:
        return False
    return urlsplit(origin).netloc.lower() == host.lower()


# The value runs to the next parameter, whitespace, or quote -- uvicorn
# wraps the request target in double quotes. No word boundary before
# `token` and case-insensitive: over-redacting `boresight_token=` or a
# `TOKEN=` costs nothing, under-redacting costs the credential.
_TOKEN_IN_TEXT = re.compile(r"(token=)[^&\s\"'#]+", re.IGNORECASE)


def redact_token(text: str) -> str:
    return _TOKEN_IN_TEXT.sub(rf"\g<1>{REDACTED}", text)


class TokenRedactionFilter(logging.Filter):
    """Blank out any `token=<value>` before a record is emitted.

    Generic, not a match on the configured token: a wrong token is a
    credential attempt too, often a character away from the real one,
    and this way the filter needs no access to configuration. Uvicorn
    passes the request target as a `%s` argument rather than baking it
    into the message, so args are rewritten as well as the message.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_token(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                redact_token(arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: redact_token(arg) if isinstance(arg, str) else arg
                for key, arg in record.args.items()
            }
        return True


def install_log_redaction(
    logger_names: tuple[str, ...] = UVICORN_REQUEST_LOGGERS,
) -> None:
    """Attach the redaction filter to uvicorn's request loggers, once.

    On the loggers rather than their handlers: uvicorn's `dictConfig`
    replaces handlers wholesale but only ever adds logger filters, so
    installing this before `uvicorn.run` survives it. Defence in depth
    -- the phone stops putting the token in URLs after its first
    request, but that request, the ESP32 and any hand-typed URL still
    do.
    """
    for name in logger_names:
        logger = logging.getLogger(name)
        if not any(isinstance(f, TokenRedactionFilter) for f in logger.filters):
            logger.addFilter(TokenRedactionFilter())


def resolve_certificate(config: ServerConfig) -> tuple[Path, Path]:
    """Return the certificate and key to serve with, generating if needed.

    A generated certificate is persisted and reused. Regenerating per
    start would invalidate the phone's one-time acceptance of it every
    time the server restarts, which is the difference between a single
    interstitial and an endless one.

    Reused, that is, while it still fits. A certificate naming the
    address the PC had last week does not match the URL printed today,
    and the phone rejects it however often it was accepted before. So a
    persisted certificate is checked first and replaced when it does not
    cover the advertised host, is about to expire, or cannot be read. A
    supplied certificate is the operator's business and is never looked
    at.
    """
    if config.certfile and config.keyfile:
        return config.certfile, config.keyfile

    cert_dir = config.cert_dir
    certfile = cert_dir / CERT_NAME
    keyfile = cert_dir / KEY_NAME
    host = config.advertised_host()
    if not (certfile.exists() and keyfile.exists()):
        cert_dir.mkdir(parents=True, exist_ok=True)
        _write_self_signed(certfile, keyfile, [host])
        logger.info("generated a TLS certificate for %s at %s", host, certfile)
        return certfile, keyfile

    persisted = _read_certificate(certfile)
    now = dt.datetime.now(dt.UTC)
    reason = _stale_reason(persisted, host, now)
    if reason is None:
        return certfile, keyfile

    previous_hosts = persisted.hosts if persisted else []
    hosts = _dedupe([host, *previous_hosts])[:CERT_MAX_HOSTS]
    _write_self_signed(certfile, keyfile, hosts)
    logger.warning(
        "TLS certificate %s %s, so a new one was generated covering %s.\n"
        "  Phones must accept the certificate again (the browser warning "
        "returns once).\n"
        "  Its SHA-256 fingerprint changed:\n"
        "    old  %s\n"
        "    new  %s\n"
        "  A device that pins the certificate must be given the new one: "
        "for the ESP32-CAM, copy %s to firmware/boresight-cam/main/"
        "server_cert.pem and rebuild and reflash it.",
        certfile,
        reason,
        ", ".join(hosts),
        persisted.fingerprint if persisted else "(unreadable)",
        certificate_fingerprint(certfile),
        certfile,
    )
    return certfile, keyfile


@dataclass(frozen=True)
class _PersistedCertificate:
    hosts: list[str]  # SAN entries other than localhost/127.0.0.1, in order
    not_valid_after: dt.datetime
    fingerprint: str


def _read_certificate(certfile: Path) -> _PersistedCertificate | None:
    """What a persisted certificate covers, or None if it cannot be read.

    Unreadable is not fatal: the file is the server's own, and a
    truncated write should cost a regeneration, not a startup traceback.
    """
    from cryptography import x509

    try:
        certificate = x509.load_pem_x509_certificate(certfile.read_bytes())
        names = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except OSError, ValueError, x509.ExtensionNotFound:
        return None

    # In the order written, which is most recent first: the host being
    # advertised at generation always leads.
    hosts = [
        str(name.value)
        for name in names
        if isinstance(name, (x509.IPAddress, x509.DNSName))
    ]
    return _PersistedCertificate(
        hosts=_dedupe(hosts),
        not_valid_after=certificate.not_valid_after_utc,
        fingerprint=_fingerprint(certificate),
    )


def _stale_reason(
    persisted: _PersistedCertificate | None, host: str, now: dt.datetime
) -> str | None:
    """Why a persisted certificate must be replaced, or None to keep it."""
    if persisted is None:
        return "could not be read"
    if not _covers(persisted.hosts, host):
        covered = ", ".join(persisted.hosts) or "only localhost"
        return f"does not cover {host} (it covers {covered})"
    expires = persisted.not_valid_after
    if expires <= now:
        return f"expired on {expires:%Y-%m-%d}"
    if expires - now <= dt.timedelta(days=CERT_RENEW_BEFORE_DAYS):
        return f"expires on {expires:%Y-%m-%d}"
    return None


def _covers(hosts: list[str], host: str) -> bool:
    """Whether a SAN list matches the host a client will dial.

    Typed, as a browser matches: an address against addresses (so two
    spellings of one IPv6 address agree), a name against names without
    regard to case.
    """
    normalised = _normalise_host(host)
    if normalised in _ALWAYS_COVERED:
        return True
    return normalised in {_normalise_host(h) for h in hosts}


def _normalise_host(host: str) -> str:
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return host.lower()


def _dedupe(hosts: list[str]) -> list[str]:
    seen: set[str] = set()
    unique = []
    for host in hosts:
        key = _normalise_host(host)
        if key not in seen and key not in _ALWAYS_COVERED:
            seen.add(key)
            unique.append(host)
    return unique


def certificate_fingerprint(certfile: Path) -> str:
    """SHA-256 over the certificate's DER, as colon-separated hex.

    Printed at startup so a device that embeds the certificate as its
    only trust anchor can be checked against the one being served. The
    device logs the same figure for what it embedded; two lines to
    compare beats a TLS handshake that just fails.
    """
    from cryptography import x509

    return _fingerprint(x509.load_pem_x509_certificate(certfile.read_bytes()))


def _fingerprint(certificate) -> str:
    from cryptography.hazmat.primitives import hashes

    return ":".join(f"{byte:02X}" for byte in certificate.fingerprint(hashes.SHA256()))


def _write_self_signed(
    certfile: Path,
    keyfile: Path,
    hosts: list[str],
    valid_days: int = CERT_VALID_DAYS,
) -> None:
    """Generate a certificate covering `hosts`, the first as its CN."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hosts[0])])

    # The phone dials an IP, not a name, so the address has to appear in
    # subjectAltName or the certificate will not match the URL even
    # after the user accepts it.
    alt_names: list[x509.GeneralName] = []
    for host in [*_dedupe(hosts), *_ALWAYS_COVERED]:
        try:
            alt_names.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            alt_names.append(x509.DNSName(host))

    now = dt.datetime.now(dt.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=valid_days))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    keyfile.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    keyfile.chmod(0o600)
    certfile.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
