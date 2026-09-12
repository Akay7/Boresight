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
import secrets
import socket
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7331
DEFAULT_CERT_DIR = Path(".boresight")
CERT_NAME = "server.crt"
KEY_NAME = "server.key"
CERT_VALID_DAYS = 825

TOKEN_QUERY_PARAM = "token"


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


def presented_token(query_token: str | None, authorization: str | None) -> str | None:
    """Pull the token from either place a client can put it.

    A browser cannot set headers on a WebSocket handshake, so the query
    parameter is not a convenience -- it is the only mechanism the phone
    has. Everything else may use a bearer header.
    """
    if query_token:
        return query_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[len("bearer ") :].strip()
    return None


def resolve_certificate(config: ServerConfig) -> tuple[Path, Path]:
    """Return the certificate and key to serve with, generating if needed.

    A generated certificate is persisted and reused. Regenerating per
    start would invalidate the phone's one-time acceptance of it every
    time the server restarts, which is the difference between a single
    interstitial and an endless one.
    """
    if config.certfile and config.keyfile:
        return config.certfile, config.keyfile

    cert_dir = config.cert_dir
    certfile = cert_dir / CERT_NAME
    keyfile = cert_dir / KEY_NAME
    if certfile.exists() and keyfile.exists():
        return certfile, keyfile

    cert_dir.mkdir(parents=True, exist_ok=True)
    _write_self_signed(certfile, keyfile, config.advertised_host())
    return certfile, keyfile


def _write_self_signed(certfile: Path, keyfile: Path, host: str) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])

    # The phone dials an IP, not a name, so the address has to appear in
    # subjectAltName or the certificate will not match the URL even
    # after the user accepts it.
    alt_names: list[x509.GeneralName] = [x509.DNSName("localhost")]
    try:
        alt_names.append(x509.IPAddress(ipaddress.ip_address(host)))
    except ValueError:
        alt_names.append(x509.DNSName(host))
    alt_names.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))

    now = dt.datetime.now(dt.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=CERT_VALID_DAYS))
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
