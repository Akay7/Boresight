import pytest
from fastapi.testclient import TestClient

from boresight.inject import FakeCursorBackend
from boresight.server import create_app


@pytest.fixture
def fake_backend() -> FakeCursorBackend:
    return FakeCursorBackend()


@pytest.fixture
def client(fake_backend: FakeCursorBackend) -> TestClient:
    app = create_app(backend_factory=lambda: fake_backend)
    with TestClient(app) as test_client:
        yield test_client
