from fastapi.testclient import TestClient

from boresight.inject import FakeCursorBackend


def test_valid_move_invokes_backend_with_matching_coordinates(
    client: TestClient, fake_backend: FakeCursorBackend
) -> None:
    response = client.post("/cursor/move", json={"x": 0.5, "y": 0.5})

    assert response.status_code == 204
    assert fake_backend.calls == [(0.5, 0.5)]


def test_out_of_range_coordinates_are_rejected(
    client: TestClient, fake_backend: FakeCursorBackend
) -> None:
    response = client.post("/cursor/move", json={"x": 1.5, "y": -0.1})

    assert response.status_code == 422
    assert fake_backend.calls == []


def test_non_numeric_coordinates_are_rejected(
    client: TestClient, fake_backend: FakeCursorBackend
) -> None:
    response = client.post("/cursor/move", json={"x": "left", "y": 0.5})

    assert response.status_code == 422
    assert fake_backend.calls == []


def test_repeated_calls_record_distinct_absolute_positions(
    client: TestClient, fake_backend: FakeCursorBackend
) -> None:
    client.post("/cursor/move", json={"x": 0.1, "y": 0.1})
    client.post("/cursor/move", json={"x": 0.9, "y": 0.2})

    assert fake_backend.calls == [(0.1, 0.1), (0.9, 0.2)]
