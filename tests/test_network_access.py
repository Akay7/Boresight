"""Reaching the server from another device, safely.

This is the change that first exposes the server beyond loopback, so
these are the tests that stand between "a phone can use it" and "so can
anything else on the Wi-Fi". The asset being protected is the operator's
mouse cursor, and the failure mode is silent: an open server behaves
identically to a closed one from the operator's chair.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from boresight.inject import FakeCursorBackend
from boresight.netaccess import (
    TOKEN_COOKIE_NAME,
    InsecureConfigurationError,
    ServerConfig,
    TokenRedactionFilter,
    install_log_redaction,
    is_loopback,
    origin_matches_host,
    presented_token,
    redact_token,
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
    """The link is on the page and carries no token -- the cookie set
    by loading the page authorizes it. A guarded server is the one the
    phone can reach at all, so assert both halves: the link exists, and
    its destination is reachable by the browser that loaded the page."""
    with _client(backend, TOKEN) as client:
        page = client.get(f"/?token={TOKEN}").text
        script = client.get("/capture.js").text

        assert 'id="marker-sheet"' in page
        assert 'sameOriginUrl("markers")' in script
        assert client.get("/markers").status_code == 200


def test_the_client_page_loads_its_own_script_through_the_guard(
    backend: FakeCursorBackend,
) -> None:
    """capture.js is guarded like everything else, and the page loads it
    with a plain src: the response to the page itself set the cookie, so
    the script request is authorized without the token in its URL --
    where it would otherwise land in the access log once per load."""
    with _client(backend, TOKEN) as client:
        page = client.get(f"/?token={TOKEN}").text

        assert '<script src="capture.js"></script>' in page
        assert "token=" not in page
        assert client.get("/capture.js").status_code == 200


def test_the_client_script_puts_no_token_in_urls(backend: FakeCursorBackend) -> None:
    """Source-level, since there is no browser here: the script removes
    the token from the address bar and never appends one to a request."""
    with _client(backend, TOKEN) as client:
        client.get(f"/?token={TOKEN}")
        script = client.get("/capture.js").text

    assert "history.replaceState" in script
    assert "searchParams.set(" not in script


def test_the_client_page_has_an_overlay_margin_control(
    backend: FakeCursorBackend,
) -> None:
    """The stepper exists, and the script wires it to the same route the
    server exposes for it, the same way marker-source selection is
    checked above."""
    with _client(backend, TOKEN) as client:
        page = client.get(f"/?token={TOKEN}").text
        script = client.get(f"/capture.js?token={TOKEN}").text

        assert 'id="overlay-margin-down"' in page
        assert 'id="overlay-margin-up"' in page
        assert 'id="overlay-margin-value"' in page
        assert "markers/overlay-margin" in script


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


# --- Session cookie ---------------------------------------------------


def _set_cookie_headers(response) -> list[str]:
    return [
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith(f"{TOKEN_COOKIE_NAME}=")
    ]


def test_a_valid_query_token_sets_the_session_cookie(
    backend: FakeCursorBackend,
) -> None:
    with _client(backend, TOKEN) as client:
        response = client.get(f"/?token={TOKEN}")

    [cookie] = _set_cookie_headers(response)
    attributes = [part.strip().lower() for part in cookie.split(";")]
    assert attributes[0] == f"{TOKEN_COOKIE_NAME}={TOKEN}".lower()
    assert "httponly" in attributes
    assert "samesite=strict" in attributes
    assert "path=/" in attributes
    assert any(part.startswith("max-age=") for part in attributes)
    # Plain HTTP is a supported path (adb reverse to localhost); a
    # Secure cookie would never be stored there.
    assert "secure" not in attributes


def test_the_session_cookie_is_secure_only_under_tls(
    backend: FakeCursorBackend,
) -> None:
    app = create_app(
        backend_factory=lambda: backend, config=ServerConfig(token=TOKEN, tls=True)
    )
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get(f"/?token={TOKEN}")

    [cookie] = _set_cookie_headers(response)
    assert "secure" in [part.strip().lower() for part in cookie.split(";")]


def test_an_invalid_query_token_sets_no_cookie(backend: FakeCursorBackend) -> None:
    with _client(backend, TOKEN) as client:
        response = client.get("/?token=nearly-right")

    assert response.status_code == 401
    assert _set_cookie_headers(response) == []


def test_a_bearer_request_is_not_issued_a_cookie(backend: FakeCursorBackend) -> None:
    """Callers using the header chose it to stay stateless."""
    with _client(backend, TOKEN) as client:
        response = client.get("/", headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == 200
    assert _set_cookie_headers(response) == []


def test_the_cookie_alone_authorizes_http(backend: FakeCursorBackend) -> None:
    cookie = {"Cookie": f"{TOKEN_COOKIE_NAME}={TOKEN}"}
    with _client(backend, TOKEN) as client:
        assert client.get("/", headers=cookie).status_code == 200
        response = client.post("/cursor/move", json=MOVE, headers=cookie)

    assert response.status_code == 204
    assert backend.calls == [(0.5, 0.5)]


def test_the_cookie_issued_by_the_page_carries_later_requests(
    backend: FakeCursorBackend,
) -> None:
    """End to end through the client's own cookie jar, as a browser
    would: one URL with the token, then nothing but the cookie."""
    with _client(backend, TOKEN) as client:
        assert client.get(f"/?token={TOKEN}").status_code == 200
        assert client.post("/cursor/move", json=MOVE).status_code == 204
        with client.websocket_connect(FRAME_SOCKET_PATH):
            pass

    assert backend.calls == [(0.5, 0.5)]


def test_a_wrong_cookie_is_rejected(backend: FakeCursorBackend) -> None:
    cookie = {"Cookie": f"{TOKEN_COOKIE_NAME}=nearly-right"}
    with _client(backend, TOKEN) as client:
        response = client.post("/cursor/move", json=MOVE, headers=cookie)
        with pytest.raises(WebSocketDisconnect) as caught:
            with client.websocket_connect(FRAME_SOCKET_PATH, headers=cookie):
                pass

    assert response.status_code == 401
    assert caught.value.code == 1008
    assert backend.calls == []


def test_a_query_token_overrides_a_stale_cookie(backend: FakeCursorBackend) -> None:
    """A cookie from a previous `--token-auto` run must not mask the URL
    the operator just opened -- and that URL re-issues the cookie."""
    with _client(backend, TOKEN) as client:
        response = client.get(
            f"/?token={TOKEN}", headers={"Cookie": f"{TOKEN_COOKIE_NAME}=old-run"}
        )
        rejected = client.get(
            "/?token=nearly-right", headers={"Cookie": f"{TOKEN_COOKIE_NAME}={TOKEN}"}
        )

    assert response.status_code == 200
    assert len(_set_cookie_headers(response)) == 1
    # An explicit wrong token is not rescued by a right cookie.
    assert rejected.status_code == 401


def test_the_cookie_alone_authorizes_the_frame_socket(
    backend: FakeCursorBackend,
) -> None:
    """The point of the cookie: the phone's socket URL no longer needs
    the token, so the handshake line uvicorn logs no longer has one."""
    cookie = {"Cookie": f"{TOKEN_COOKIE_NAME}={TOKEN}"}
    with _client(backend, TOKEN) as client:
        with client.websocket_connect(FRAME_SOCKET_PATH, headers=cookie):
            pass
        with client.websocket_connect(
            FRAME_SOCKET_PATH,
            headers={**cookie, "Origin": "http://testserver"},
        ):
            pass


def test_a_foreign_origin_cannot_ride_the_cookie(backend: FakeCursorBackend) -> None:
    """SameSite ignores ports, and a WebSocket handshake ignores CORS: a
    page on another port of this host would otherwise get the cookie
    attached to a socket that moves the cursor."""
    foreign = {
        "Cookie": f"{TOKEN_COOKIE_NAME}={TOKEN}",
        "Origin": "http://testserver:8080",
    }
    with _client(backend, TOKEN) as client:
        response = client.post("/cursor/move", json=MOVE, headers=foreign)
        with pytest.raises(WebSocketDisconnect) as caught:
            with client.websocket_connect(FRAME_SOCKET_PATH, headers=foreign):
                pass

    assert response.status_code == 401
    assert caught.value.code == 1008
    assert backend.calls == []


def test_an_explicit_token_is_not_subject_to_the_origin_check(
    backend: FakeCursorBackend,
) -> None:
    """Not ambient: whoever put the token in the URL or header meant to."""
    with _client(backend, TOKEN) as client:
        with client.websocket_connect(
            f"{FRAME_SOCKET_PATH}?token={TOKEN}",
            headers={"Origin": "http://elsewhere"},
        ):
            pass
        response = client.post(
            "/cursor/move",
            json=MOVE,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Origin": "http://elsewhere",
            },
        )

    assert response.status_code == 204


def test_the_frame_socket_accepts_a_bearer_header(backend: FakeCursorBackend) -> None:
    with _client(backend, TOKEN) as client:
        with client.websocket_connect(
            FRAME_SOCKET_PATH, headers={"Authorization": f"Bearer {TOKEN}"}
        ):
            pass


def test_origin_comparison() -> None:
    assert origin_matches_host(None, "host:7331") is True
    assert origin_matches_host("https://host:7331", "host:7331") is True
    assert origin_matches_host("https://HOST:7331", "host:7331") is True
    assert origin_matches_host("https://host:8080", "host:7331") is False
    assert origin_matches_host("https://other:7331", "host:7331") is False
    assert origin_matches_host("https://host:7331", None) is False


# --- Log redaction ---------------------------------------------------


def _record(msg: str, args) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, msg, args, None
    )


def test_redaction_replaces_any_token_value() -> None:
    assert redact_token(f"GET /?token={TOKEN} HTTP/1.1") == "GET /?token=*** HTTP/1.1"
    assert redact_token(f"/m?a=1&token={TOKEN}&b=2") == "/m?a=1&token=***&b=2"
    # Wrong tokens are credential attempts too.
    assert redact_token('"GET /?token=nearly-right"') == '"GET /?token=***"'
    assert redact_token("/?other=1") == "/?other=1"


def test_the_filter_redacts_uvicorn_access_args() -> None:
    """Uvicorn's own shape: the request target is a `%s` argument."""
    record = _record(
        '%s - "%s %s HTTP/%s" %d',
        ("10.0.0.2:5000", "GET", f"/capture.js?token={TOKEN}", "1.1", 200),
    )

    assert TokenRedactionFilter().filter(record) is True
    message = record.getMessage()
    assert TOKEN not in message
    assert "/capture.js?token=***" in message
    assert message.endswith(" 200")


def test_the_filter_redacts_the_websocket_handshake_line() -> None:
    record = _record(
        '%s - "WebSocket %s" [accepted]',
        ("10.0.0.2:5000", f"/ws/frames?token={TOKEN}"),
    )

    TokenRedactionFilter().filter(record)

    assert (
        record.getMessage()
        == '10.0.0.2:5000 - "WebSocket /ws/frames?token=***" [accepted]'
    )


def test_the_filter_redacts_a_preformatted_message_and_mapping_args() -> None:
    inline = _record(f"GET /?token={TOKEN}", None)
    mapping = _record("%(path)s", ({"path": f"/?token={TOKEN}"},))

    TokenRedactionFilter().filter(inline)
    TokenRedactionFilter().filter(mapping)

    assert inline.getMessage() == "GET /?token=***"
    assert mapping.getMessage() == "/?token=***"


def test_installed_redaction_applies_to_emitted_records(caplog) -> None:
    name = "test.boresight.redaction"
    install_log_redaction((name,))
    install_log_redaction((name,))  # idempotent

    logger = logging.getLogger(name)
    with caplog.at_level(logging.INFO, logger=name):
        logger.info('%s - "WebSocket %s" 403', "peer", "/ws/frames?token=guess")

    assert sum(isinstance(f, TokenRedactionFilter) for f in logger.filters) == 1
    assert "guess" not in caplog.text
    assert "token=***" in caplog.text


def test_main_installs_redaction_before_serving(monkeypatch) -> None:
    from boresight import server

    seen: list[bool] = []

    def fake_run(*args, **kwargs) -> None:
        seen.extend(
            any(
                isinstance(f, TokenRedactionFilter)
                for f in logging.getLogger(name).filters
            )
            for name in ("uvicorn.access", "uvicorn.error")
        )

    monkeypatch.setattr("uvicorn.run", fake_run)
    monkeypatch.setattr(server, "create_app", lambda **kwargs: object())
    server.main(["--token", TOKEN])

    assert seen == [True, True]


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


def test_the_overlay_margin_flag_reaches_create_app(monkeypatch) -> None:
    from boresight import server

    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)
    calls = []
    monkeypatch.setattr(
        server,
        "create_app",
        lambda **kwargs: calls.append(kwargs) or object(),
    )

    server.main(["--overlay-extra-margin-px", "40"])

    assert calls[0]["overlay_extra_margin_px"] == 40


def test_the_overlay_margin_flag_defaults_to_zero(monkeypatch) -> None:
    from boresight import server

    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)
    calls = []
    monkeypatch.setattr(
        server,
        "create_app",
        lambda **kwargs: calls.append(kwargs) or object(),
    )

    server.main([])

    assert calls[0]["overlay_extra_margin_px"] == 0


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
    assert presented_token(None, None, "c") == "c"
    assert presented_token("q", None, "c") == "q"  # the URL beats a stale cookie
    assert presented_token(None, "Bearer h", "c") == "h"


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


def _san(certfile: Path) -> list[str]:
    from cryptography import x509

    certificate = x509.load_pem_x509_certificate(certfile.read_bytes())
    names = certificate.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value
    return [str(name.value) for name in names]


def _tls(host: str, cert_dir: Path) -> ServerConfig:
    return ServerConfig(host=host, token=TOKEN, tls=True, cert_dir=cert_dir)


def test_a_certificate_for_a_previous_address_is_regenerated(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The PC's DHCP lease changed: the old certificate no longer matches
    the URL being printed, and the phone would reject it however often
    it was accepted before."""
    from boresight.netaccess import certificate_fingerprint

    certfile, _key = resolve_certificate(_tls("192.168.1.20", tmp_path))
    old = certificate_fingerprint(certfile)

    with caplog.at_level(logging.WARNING, logger="boresight"):
        resolve_certificate(_tls("192.168.1.30", tmp_path))

    new = certificate_fingerprint(certfile)
    assert new != old
    assert "192.168.1.30" in _san(certfile)
    message = caplog.text
    assert "does not cover 192.168.1.30" in message
    assert "accept the certificate again" in message
    assert old in message and new in message
    assert "ESP32-CAM" in message


def test_returning_to_a_remembered_address_does_not_regenerate(
    tmp_path: Path,
) -> None:
    """Home, office, home: one regeneration per network, not per move."""
    resolve_certificate(_tls("192.168.1.20", tmp_path))
    certfile, _key = resolve_certificate(_tls("10.0.0.5", tmp_path))
    remembered = certfile.read_bytes()

    resolve_certificate(_tls("192.168.1.20", tmp_path))
    resolve_certificate(_tls("10.0.0.5", tmp_path))

    assert certfile.read_bytes() == remembered
    assert _san(certfile)[:2] == ["10.0.0.5", "192.168.1.20"]


def test_remembered_addresses_are_bounded(tmp_path: Path) -> None:
    from boresight.netaccess import CERT_MAX_HOSTS

    for last_octet in range(1, CERT_MAX_HOSTS + 3):
        certfile, _key = resolve_certificate(_tls(f"10.0.0.{last_octet}", tmp_path))

    san = _san(certfile)
    newest = CERT_MAX_HOSTS + 2
    assert san[0] == f"10.0.0.{newest}"
    assert "10.0.0.1" not in san  # the oldest fell off first
    assert len(san) == CERT_MAX_HOSTS + 2  # plus localhost and 127.0.0.1
    assert {"localhost", "127.0.0.1"} <= set(san)


def test_a_hostname_is_covered_by_name(tmp_path: Path) -> None:
    certfile, _key = resolve_certificate(_tls("gamepc.local", tmp_path))
    first = certfile.read_bytes()
    assert "gamepc.local" in _san(certfile)

    resolve_certificate(_tls("GamePC.local", tmp_path))  # names ignore case
    assert certfile.read_bytes() == first

    resolve_certificate(_tls("other.local", tmp_path))
    assert "other.local" in _san(certfile)


def test_an_expiring_certificate_is_regenerated(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from boresight.netaccess import (
        CERT_NAME,
        CERT_RENEW_BEFORE_DAYS,
        KEY_NAME,
        _write_self_signed,
    )

    certfile, keyfile = tmp_path / CERT_NAME, tmp_path / KEY_NAME
    _write_self_signed(
        certfile, keyfile, ["192.168.1.20"], valid_days=CERT_RENEW_BEFORE_DAYS - 1
    )
    expiring = certfile.read_bytes()

    with caplog.at_level(logging.WARNING, logger="boresight"):
        resolve_certificate(_tls("192.168.1.20", tmp_path))

    assert certfile.read_bytes() != expiring
    assert "expires on" in caplog.text
    assert "192.168.1.20" in _san(certfile)


def test_an_expired_certificate_is_regenerated(tmp_path: Path) -> None:
    from boresight.netaccess import CERT_NAME, KEY_NAME, _write_self_signed

    certfile, keyfile = tmp_path / CERT_NAME, tmp_path / KEY_NAME
    _write_self_signed(certfile, keyfile, ["192.168.1.20"], valid_days=0)
    expired = certfile.read_bytes()

    resolve_certificate(_tls("192.168.1.20", tmp_path))

    assert certfile.read_bytes() != expired


def test_an_unreadable_certificate_is_regenerated(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A truncated write must cost a regeneration, not a traceback."""
    from boresight.netaccess import CERT_NAME, KEY_NAME

    (tmp_path / CERT_NAME).write_text("-----BEGIN CERTIFICATE-----\ntrunc")
    (tmp_path / KEY_NAME).write_text("junk")

    with caplog.at_level(logging.WARNING, logger="boresight"):
        certfile, _key = resolve_certificate(_tls("192.168.1.20", tmp_path))

    assert "192.168.1.20" in _san(certfile)
    assert "could not be read" in caplog.text


def test_a_certificate_from_before_this_check_is_kept_when_it_fits(
    tmp_path: Path,
) -> None:
    """Certificates already on disk put localhost first; that layout
    must still read as covering its address."""
    import datetime as dt
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    from boresight.netaccess import CERT_NAME, KEY_NAME

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "192.168.1.20")])
    now = dt.datetime.now(dt.UTC)
    san = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("192.168.1.20")),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    legacy = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + dt.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .sign(key, hashes.SHA256())
    ).public_bytes(serialization.Encoding.PEM)
    (tmp_path / CERT_NAME).write_bytes(legacy)
    (tmp_path / KEY_NAME).write_bytes(b"key")

    certfile, _key = resolve_certificate(_tls("192.168.1.20", tmp_path))

    assert certfile.read_bytes() == legacy


def test_a_supplied_certificate_is_never_regenerated(tmp_path: Path) -> None:
    """Even one for another address, or long expired: it is the
    operator's, and the server has no business replacing it."""
    from boresight.netaccess import _write_self_signed

    certfile = tmp_path / "mine.crt"
    keyfile = tmp_path / "mine.key"
    _write_self_signed(certfile, keyfile, ["10.9.9.9"], valid_days=0)
    supplied = certfile.read_bytes()
    config = ServerConfig(
        host="192.168.1.20",
        token=TOKEN,
        tls=True,
        certfile=certfile,
        keyfile=keyfile,
        cert_dir=tmp_path / "unused",
    )

    assert resolve_certificate(config) == (certfile, keyfile)
    assert certfile.read_bytes() == supplied
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


# --- Connection details for a headless device ------------------------


def test_the_certificate_fingerprint_is_sha256_over_der(tmp_path: Path) -> None:
    import hashlib
    import ssl

    from boresight.netaccess import certificate_fingerprint

    certfile, _key = resolve_certificate(
        ServerConfig(host="127.0.0.1", tls=True, cert_dir=tmp_path)
    )
    der = ssl.PEM_cert_to_DER_cert(certfile.read_text())

    fingerprint = certificate_fingerprint(certfile)

    assert len(fingerprint.split(":")) == 32
    assert fingerprint.replace(":", "") == hashlib.sha256(der).hexdigest().upper()


def test_the_fingerprint_is_stable_across_restarts(tmp_path: Path) -> None:
    """A device pins the certificate it was flashed with, so a restart
    that changed it would silently strand every device."""
    from boresight.netaccess import certificate_fingerprint

    config = ServerConfig(host="127.0.0.1", tls=True, cert_dir=tmp_path)

    first = certificate_fingerprint(resolve_certificate(config)[0])
    second = certificate_fingerprint(resolve_certificate(config)[0])

    assert first == second


def _run_main(monkeypatch, argv: list[str]) -> None:
    from boresight import server

    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "create_app", lambda **kwargs: object())
    server.main(argv)


def test_plain_text_device_details_are_printed(monkeypatch, capsys) -> None:
    _run_main(monkeypatch, ["--host", "192.168.1.20", "--token", TOKEN])

    out = capsys.readouterr().out

    assert "host    192.168.1.20" in out
    assert "port    7331" in out
    assert f"path    {FRAME_SOCKET_PATH}" in out
    assert "tls     off" in out
    assert f"token   {TOKEN}" in out
    assert "sha256" not in out


def test_tls_device_details_carry_the_certificate_fingerprint(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    from boresight.netaccess import certificate_fingerprint

    certfile, keyfile = resolve_certificate(
        ServerConfig(host="127.0.0.1", tls=True, cert_dir=tmp_path)
    )

    _run_main(
        monkeypatch, ["--tls", "--certfile", str(certfile), "--keyfile", str(keyfile)]
    )

    out = capsys.readouterr().out
    assert "tls     on" in out
    assert "token   (none)" in out
    assert f"cert    {certfile}" in out
    assert f"sha256  {certificate_fingerprint(certfile)}" in out
