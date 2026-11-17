"""The server's announcement on the local network (`discovery.py`).

Driven with a fake zeroconf throughout, so nothing here reaches the
network: what is checked is what the server would announce, when it
would, and that it withdraws it. A live check against a real network is
`avahi-browse -rt _boresight._tcp` (see README, "Finding the server").
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boresight import server
from boresight.discovery import (
    SERVICE_TYPE,
    Announcer,
    announceable_address,
    service_properties,
)
from boresight.inject import FakeCursorBackend
from boresight.server import FRAME_SOCKET_PATH, create_app

TOKEN = "sekrit-token-value"


class FakeZeroconf:
    """Records what an `AsyncZeroconf` would have been asked to do.

    Like the real one, registering and unregistering return a task that
    does the work; `settled` counts the ones awaited to the end, which is
    what actually sends the announcement and its goodbye.
    """

    def __init__(self) -> None:
        self.registered: list = []
        self.unregistered: list = []
        self.closed = False
        self.allow_name_change = None
        self.settled = 0

    async def _work(self) -> None:
        self.settled += 1

    async def async_register_service(self, info, allow_name_change=False):
        self.registered.append(info)
        self.allow_name_change = allow_name_change
        return asyncio.ensure_future(self._work())

    async def async_unregister_service(self, info):
        self.unregistered.append(info)
        return asyncio.ensure_future(self._work())

    async def async_close(self):
        self.closed = True


def _announcer(fake: FakeZeroconf, *, tls: bool = False) -> Announcer:
    return Announcer(
        address="192.168.1.40",
        port=7331,
        tls=tls,
        path=FRAME_SOCKET_PATH,
        hostname="gaming-pc.example.lan",
        zeroconf_factory=lambda: fake,
    )


def test_the_announcement_says_where_the_frame_socket_is() -> None:
    fake = FakeZeroconf()

    asyncio.run(_announcer(fake).start())

    [info] = fake.registered
    assert info.type == SERVICE_TYPE == "_boresight._tcp.local."
    assert info.name == f"Boresight on gaming-pc.{SERVICE_TYPE}"
    assert info.port == 7331
    assert [str(ipaddress.ip_address(a)) for a in info.addresses] == ["192.168.1.40"]
    assert info.properties == {b"path": b"/ws/frames", b"tls": b"0", b"v": b"1"}
    # Not the machine's own <hostname>.local, which Avahi may hold.
    assert info.server == "boresight-gaming-pc.local."
    # A second server on the network gets a numbered name, not an error.
    assert fake.allow_name_change is True


def test_tls_is_announced() -> None:
    fake = FakeZeroconf()
    asyncio.run(_announcer(fake, tls=True).start())
    assert fake.registered[0].properties[b"tls"] == b"1"
    assert service_properties("/ws/frames", tls=True)["tls"] == "1"


def test_stopping_withdraws_the_announcement() -> None:
    fake = FakeZeroconf()
    announcer = _announcer(fake)

    async def run() -> None:
        await announcer.start()
        await announcer.stop()
        await announcer.stop()  # twice is harmless

    asyncio.run(run())
    assert fake.unregistered == fake.registered
    # Both tasks were seen through: the goodbye went out before closing.
    assert fake.settled == 2
    assert fake.closed


def test_stopping_what_never_started_does_nothing() -> None:
    asyncio.run(_announcer(FakeZeroconf()).stop())


def test_a_failed_announcement_is_logged_not_fatal(caplog) -> None:
    def broken():
        raise OSError("no multicast here")

    announcer = Announcer(
        address="192.168.1.40",
        port=7331,
        tls=False,
        path=FRAME_SOCKET_PATH,
        zeroconf_factory=broken,
    )
    with caplog.at_level(logging.WARNING, logger="boresight"):
        asyncio.run(announcer.start())
        asyncio.run(announcer.stop())
    assert "not announcing on the local network: no multicast here" in caplog.text


@pytest.mark.parametrize(
    ("address", "announced"),
    [
        ("192.168.1.40", "192.168.1.40"),
        ("127.0.0.1", None),
        ("0.0.0.0", None),
        ("::1", None),
        ("fe80::1", None),
        ("localhost", None),
        ("no-such-host.invalid", None),
    ],
)
def test_only_a_reachable_ipv4_address_is_announced(
    address: str, announced: str | None
) -> None:
    assert announceable_address(address) == announced


class RecordingAnnouncer:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def start(self) -> None:
        self.events.append("start")

    async def stop(self) -> None:
        self.events.append("stop")


def test_the_app_announces_while_it_runs() -> None:
    announcer = RecordingAnnouncer()
    app = create_app(backend_factory=FakeCursorBackend, announcer=announcer)

    with TestClient(app):
        assert announcer.events == ["start"]
    assert announcer.events == ["start", "stop"]


def test_an_app_built_without_an_announcer_announces_nothing() -> None:
    """The default, which every test app relies on to stay invisible."""
    with TestClient(create_app(backend_factory=FakeCursorBackend)):
        pass


# --- Wiring in server.main ------------------------------------------------


@pytest.fixture
def started(monkeypatch, tmp_path: Path):
    """Run `server.main`, capturing what the app would have been built with."""
    captured: dict = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: None)
    # Each start replaces the last, so one test can start more than once.
    monkeypatch.setattr(
        server, "create_app", lambda **kwargs: captured.update(app=kwargs)
    )
    config = tmp_path / "config.toml"

    def start(text: str, *flags: str) -> dict:
        config.write_text(text, encoding="utf-8")
        server.main(["--config", str(config), *flags])
        return captured["app"]

    return start


def test_a_network_bound_server_is_announced(started) -> None:
    app = started("", "--host", "192.168.1.20", "--token", TOKEN)

    announcer = app["announcer"]
    assert isinstance(announcer, Announcer)
    assert (announcer.address, announcer.port) == ("192.168.1.20", 7331)
    assert (announcer.path, announcer.tls) == ("/ws/frames", False)
    # Nothing the announcement is built from carries the token.
    info = announcer.service_info()
    assert TOKEN not in repr(info)
    assert all(TOKEN.encode() not in value for value in info.properties.values())


def test_a_loopback_server_is_not_announced(started) -> None:
    assert started("", "--host", "127.0.0.1")["announcer"] is None


def test_the_flag_turns_announcing_off(started) -> None:
    app = started("", "--host", "192.168.1.20", "--token", TOKEN, "--no-announce")
    assert app["announcer"] is None


def test_the_file_turns_announcing_off_and_a_flag_back_on(started) -> None:
    file = "[server]\nannounce = false\n"
    assert (
        started(file, "--host", "192.168.1.20", "--token", TOKEN)["announcer"] is None
    )
    app = started(file, "--host", "192.168.1.20", "--token", TOKEN, "--announce")
    assert app["announcer"] is not None
