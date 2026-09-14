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


def test_a_manual_move_is_exact_despite_prior_aim_derived_filter_state(
    client: TestClient, fake_backend: FakeCursorBackend
) -> None:
    """`/cursor/move` uses the raw backend from `app.state.cursor_backend`,
    not the smoothing backend `MarkerSourceController` wraps it in -- so
    a request lands exactly, regardless of what aim-derived movement the
    filter has already seen."""
    wrapped_backend = client.app.state.markers.pipeline._backend  # noqa: SLF001
    # Simulate several frames of aim-derived movement, as AimPipeline
    # would emit them, well away from the position requested below.
    for x, y in [(0.1, 0.1), (0.12, 0.09), (0.11, 0.1)]:
        wrapped_backend.move_absolute(x, y)

    response = client.post("/cursor/move", json={"x": 0.8, "y": 0.3})

    assert response.status_code == 204
    assert fake_backend.calls[-1] == (0.8, 0.3)
