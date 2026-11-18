import pytest
from fastapi.testclient import TestClient

from boresight.inject import FakeCursorBackend
from boresight.server import create_app


@pytest.fixture(autouse=True)
def _no_local_settings_file(monkeypatch, tmp_path_factory) -> None:
    """Keep the developer's own settings file out of every test.

    The server reads `.boresight/config.toml` from the directory it runs
    in, which for the test suite is the checkout. A token or a marker
    layout saved there by a real server run would otherwise reach any
    test that starts `main()` without `--config`, and its outcome would
    depend on whose checkout it ran in. Each test gets an empty directory
    instead; a test that wants a settings file still passes `--config`.
    """
    monkeypatch.setattr(
        "boresight.settings.DEFAULT_SETTINGS_PATH",
        tmp_path_factory.mktemp("settings") / "config.toml",
    )


@pytest.fixture
def fake_backend() -> FakeCursorBackend:
    return FakeCursorBackend()


@pytest.fixture
def client(fake_backend: FakeCursorBackend) -> TestClient:
    app = create_app(backend_factory=lambda: fake_backend)
    with TestClient(app) as test_client:
        yield test_client
