"""Announcing the server on the local network, so a device can find it.

An ESP32-CAM whose server address is left empty looks for a service of
type `_boresight._tcp` over multicast DNS service discovery (mDNS /
DNS-SD) before each connection attempt, and dials the address and port
it finds. That way a PC whose address changes needs no device
reconfigured.

The announcement says where the frame socket is (`path`) and whether
the server speaks TLS (`tls`, so a device built without TLS refuses a
TLS server instead of failing its handshake for no visible reason). It
never carries the token: a device presents its own, and anything on the
network can read an announcement.

Made only when the server is bound to an address other devices can
reach -- a loopback server has nothing to announce -- and only while it
runs. Inspect it with `avahi-browse -rt _boresight._tcp`.
"""

from __future__ import annotations

import inspect
import ipaddress
import logging
import socket
from collections.abc import Callable
from typing import Any

SERVICE_TYPE = "_boresight._tcp.local."
# Bumped if what the announcement promises ever changes shape.
PROTOCOL_VERSION = "1"

logger = logging.getLogger("boresight")


def service_properties(path: str, tls: bool) -> dict[str, str]:
    """The announcement's TXT record: what a device needs, and no more."""
    return {"path": path, "tls": "1" if tls else "0", "v": PROTOCOL_VERSION}


async def _settle(result: Any) -> None:
    """Await what zeroconf hands back. Its register and unregister calls
    return a task doing the actual network work; awaiting only the call
    returns before a goodbye has been sent, so a closing server would be
    left in every cache until its records' TTL ran out."""
    if inspect.isawaitable(result):
        await result


def _short_hostname(hostname: str | None) -> str:
    name = (hostname or socket.gethostname()).split(".")[0]
    return name or "server"


def instance_name(hostname: str | None = None) -> str:
    """The service instance a person sees in a browser: one per machine."""
    return f"Boresight on {_short_hostname(hostname)}"


def announceable_address(address: str) -> str | None:
    """`address` as an IPv4 address a device can dial, or None.

    A host name is resolved; loopback, unspecified and unresolvable
    addresses are not announced.
    """
    try:
        resolved = ipaddress.ip_address(address)
    except ValueError:
        try:
            resolved = ipaddress.ip_address(socket.gethostbyname(address))
        except OSError:
            return None
    if resolved.version != 4 or resolved.is_loopback or resolved.is_unspecified:
        return None
    return str(resolved)


class Announcer:
    """Registers the server for as long as it runs.

    `zeroconf_factory` makes the `AsyncZeroconf` it talks through; tests
    pass a fake, so nothing reaches the network.
    """

    def __init__(
        self,
        *,
        address: str,
        port: int,
        tls: bool,
        path: str,
        hostname: str | None = None,
        zeroconf_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.address = address
        self.port = port
        self.tls = tls
        self.path = path
        self._hostname = _short_hostname(hostname)
        self._factory = zeroconf_factory
        self._zeroconf: Any = None
        self._info: Any = None

    def service_info(self) -> Any:
        from zeroconf import ServiceInfo

        return ServiceInfo(
            SERVICE_TYPE,
            f"{instance_name(self._hostname)}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(self.address)],
            port=self.port,
            properties=service_properties(self.path, self.tls),
            # Not the machine's own `<hostname>.local`, which Avahi may
            # already hold: two responders answering for one name collide.
            server=f"boresight-{self._hostname}.local.",
        )

    async def start(self) -> None:
        """Announce. A failure is logged, never fatal: a device with an
        address configured does not need the announcement at all."""
        try:
            from zeroconf.asyncio import AsyncZeroconf
        except ImportError:
            logger.warning(
                "not announcing on the local network: the zeroconf package is "
                "missing (install the server extra)"
            )
            return
        factory = self._factory or AsyncZeroconf
        info = self.service_info()
        try:
            zeroconf = factory()
            # A second Boresight on the network gets a numbered name rather
            # than an error.
            await _settle(
                await zeroconf.async_register_service(info, allow_name_change=True)
            )
        except Exception as error:  # noqa: BLE001 - any failure: just don't
            logger.warning("not announcing on the local network: %s", error)
            return
        self._zeroconf, self._info = zeroconf, info
        logger.info(
            "announced on the local network as %r (%s at %s:%d)",
            info.name.removesuffix(f".{SERVICE_TYPE}"),
            SERVICE_TYPE.removesuffix(".local."),
            self.address,
            self.port,
        )

    async def stop(self) -> None:
        """Withdraw the announcement, if one was made."""
        if self._zeroconf is None:
            return
        try:
            await _settle(await self._zeroconf.async_unregister_service(self._info))
        finally:
            await self._zeroconf.async_close()
            self._zeroconf = self._info = None
