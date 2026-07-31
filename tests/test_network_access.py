"""Reaching the server from another device, safely.

This is the change that first exposes the server beyond loopback, so
these are the tests that stand between "a phone can use it" and "so can
anything else on the Wi-Fi". The asset being protected is the operator's
mouse cursor, and the failure mode is silent: an open server behaves
identically to a closed one from the operator's chair.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from boresight.inject import FakeCursorBackend
from boresight.netaccess import (
    InsecureConfigurationError,
    ServerConfig,
    is_loopback,
    presented_token,
    resolve_certificate,
    token_matches,
)
from boresight.server import FRAME_SOCKET_PATH, create_app

TOKEN = "correct-horse-battery-staple"
MOVE = {"x": 0.5, "y": 0.5}


@pytest.fixture
def backend() -> FakeCursorBackend:
    return FakeCursorBackend()


def _client(backend: FakeCursorBackend, token: str | None) -> TestClient:
    app = create_app(backend_factory=lambda: backend, config=ServerConfig(token=token))
    return TestClient(app)


# --- Token enforcement ------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/capture.js", "/markers", "/markers/0.svg"])
def test_an_unauthenticated_request_is_rejected(
    backend: FakeCursorBackend, path: str
) -> None:
    """Every endpoint, not merely the interesting-looking ones. The
    marker sheets reveal the layout, and the client page carries the
    connection details."""
    with _client(backend, TOKEN) as client:
        assert client.get(path).status_code == 401


def test_the_static_client_mount_is_covered_too(backend: FakeCursorBackend) -> None:
    """Not a redundant case. The client is served by a mounted
    sub-application, which route-level dependencies never reach --
    middleware is what covers it, and this asserts that choice holds."""
    with _client(backend, TOKEN) as client:
        assert client.get("/").status_code == 401
        assert client.get(f"/?token={TOKEN}").status_code == 200


def test_an_unauthenticated_move_request_moves_nothing(
    backend: FakeCursorBackend,
) -> None:
    with _client(backend, TOKEN) as client:
        response = client.post("/cursor/move", json=MOVE)

    assert response.status_code == 401
    assert backend.calls == []


def test_an_unauthenticated_socket_is_closed_rather_than_served(
    backend: FakeCursorBackend,
) -> None:
    with _client(backend, TOKEN) as client:
        with pytest.raises(WebSocketDisconnect) as caught:
            with client.websocket_connect(FRAME_SOCKET_PATH):
                pass

    # 1008 is "policy violation": the credentials were unacceptable.
    assert caught.value.code == 1008
    assert backend.calls == []


def test_a_valid_token_is_served_normally(backend: FakeCursorBackend) -> None:
    with _client(backend, TOKEN) as client:
        assert client.get(f"/?token={TOKEN}").status_code == 200
        assert client.post(f"/cursor/move?token={TOKEN}", json=MOVE).status_code == 204
        with client.websocket_connect(f"{FRAME_SOCKET_PATH}?token={TOKEN}"):
            pass

    assert backend.calls == [(0.5, 0.5)]


def test_the_client_page_links_to_the_marker_sheet(
    backend: FakeCursorBackend,
) -> None:
    """The link is on the page, but its href is filled in by the client
    script so the token survives the click. A static href would 401
    exactly when the server is guarded, which is whenever the phone can
    reach it at all -- so assert both halves: the link exists, and its
    destination is reachable with the token."""
    with _client(backend, TOKEN) as client:
        page = client.get(f"/?token={TOKEN}").text
        script = client.get(f"/capture.js?token={TOKEN}").text

        assert 'id="marker-sheet"' in page
        assert 'sameOriginUrl("markers")' in script
        assert client.get(f"/markers?token={TOKEN}").status_code == 200


def test_a_bearer_header_is_accepted_for_http(backend: FakeCursorBackend) -> None:
    """A browser cannot set headers on a WebSocket handshake, which is
    why the query parameter exists at all -- but everything else may use
    the header, and should be able to."""
    with _client(backend, TOKEN) as client:
        response = client.post(
            "/cursor/move", json=MOVE, headers={"Authorization": f"Bearer {TOKEN}"}
        )

    assert response.status_code == 204


def test_a_wrong_token_is_rejected(backend: FakeCursorBackend) -> None:
    with _client(backend, TOKEN) as client:
        assert client.get("/?token=nearly-right").status_code == 401


def test_no_token_configured_leaves_loopback_unaffected(
    backend: FakeCursorBackend,
) -> None:
    """The existing loopback workflow must not acquire a ceremony it
    does not need. Nothing is exposed, so nothing is demanded."""
    with _client(backend, None) as client:
        assert client.get("/").status_code == 200
        assert client.post("/cursor/move", json=MOVE).status_code == 204
        with client.websocket_connect(FRAME_SOCKET_PATH):
            pass

    assert backend.calls == [(0.5, 0.5)]


# --- Refusing to expose an open server --------------------------------


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "::"])
def test_a_network_bind_without_a_token_refuses_to_start(host: str) -> None:
    """A refusal, not a warning. Startup warnings are not read, and the
    thing being denied -- an open cursor-mover on a network -- is not
    something anyone has a reason to want."""
    with pytest.raises(InsecureConfigurationError, match="token is required"):
        ServerConfig(host=host).validate()


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_without_a_token_is_allowed(host: str) -> None:
    ServerConfig(host=host).validate()  # must not raise


def test_a_network_bind_with_a_token_is_allowed() -> None:
    ServerConfig(host="0.0.0.0", token=TOKEN).validate()  # must not raise


def test_an_unrecognisable_host_is_treated_as_reachable() -> None:
    """The safe direction to be wrong in is 'demand a token'."""
    assert not is_loopback("some-host.local")
    with pytest.raises(InsecureConfigurationError):
        ServerConfig(host="some-host.local").validate()


def test_the_command_line_exits_rather_than_serving(monkeypatch) -> None:
    from boresight import server

    def fail(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("uvicorn.run was reached despite an unsafe config")

    monkeypatch.setattr("uvicorn.run", fail)

    with pytest.raises(SystemExit) as caught:
        server.main(["--host", "0.0.0.0"])

    assert caught.value.code == 2


# --- Token comparison -------------------------------------------------


def test_token_comparison_handles_the_edge_cases() -> None:
    assert token_matches(None, None) is True  # nothing configured
    assert token_matches(None, "anything") is True
    assert token_matches(TOKEN, TOKEN) is True
    assert token_matches(TOKEN, None) is False
    assert token_matches(TOKEN, "") is False
    assert token_matches(TOKEN, TOKEN + "x") is False


def test_the_token_is_read_from_either_place_a_client_can_put_it() -> None:
    assert presented_token("q", None) == "q"
    assert presented_token(None, "Bearer h") == "h"
    assert presented_token(None, "bearer h") == "h"
    assert presented_token("q", "Bearer h") == "q"  # query wins
    assert presented_token(None, "Basic h") is None
    assert presented_token(None, None) is None


# --- TLS --------------------------------------------------------------


def test_a_generated_certificate_is_reused_across_restarts(tmp_path: Path) -> None:
    """Regenerating per start would invalidate the phone's one-time
    acceptance every time the server restarts, turning a single
    interstitial into an endless one."""
    config = ServerConfig(host="127.0.0.1", tls=True, cert_dir=tmp_path)

    first_cert, first_key = resolve_certificate(config)
    first_bytes = first_cert.read_bytes()

    second_cert, second_key = resolve_certificate(config)

    assert (second_cert, second_key) == (first_cert, first_key)
    assert second_cert.read_bytes() == first_bytes


def test_a_generated_key_is_not_world_readable(tmp_path: Path) -> None:
    config = ServerConfig(host="127.0.0.1", tls=True, cert_dir=tmp_path)

    _cert, key = resolve_certificate(config)

    assert key.stat().st_mode & 0o077 == 0


def test_a_supplied_certificate_is_used_as_given(tmp_path: Path) -> None:
    certfile = tmp_path / "mine.crt"
    keyfile = tmp_path / "mine.key"
    certfile.write_bytes(b"supplied cert")
    keyfile.write_bytes(b"supplied key")
    config = ServerConfig(
        tls=True, certfile=certfile, keyfile=keyfile, cert_dir=tmp_path / "unused"
    )

    assert resolve_certificate(config) == (certfile, keyfile)
    assert not (tmp_path / "unused").exists()


# --- The phone-facing URL --------------------------------------------


def test_the_printed_url_carries_the_token() -> None:
    """The token is random and nobody should be asked to transcribe it
    from a config file."""
    config = ServerConfig(host="192.168.1.20", port=8443, token=TOKEN, tls=True)

    assert config.phone_url() == f"https://192.168.1.20:8443/?{'token'}={TOKEN}"


def test_a_wildcard_bind_resolves_to_a_dialable_address() -> None:
    """`0.0.0.0` means every interface, which is not something a phone
    can connect to."""
    url = ServerConfig(host="0.0.0.0", token=TOKEN).phone_url()

    assert "0.0.0.0" not in url
    assert url.startswith("http://")


def test_plain_http_is_reflected_in_the_url_scheme() -> None:
    assert ServerConfig(host="127.0.0.1").phone_url().startswith("http://")
    assert ServerConfig(host="127.0.0.1", tls=True).phone_url().startswith("https://")
