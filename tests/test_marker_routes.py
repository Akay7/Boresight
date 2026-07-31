from fastapi.testclient import TestClient


def test_single_marker_svg_returns_requested_size(client: TestClient) -> None:
    response = client.get("/markers/0.svg", params={"size_mm": 100})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert 'width="100.0mm"' in response.text
    assert 'height="100.0mm"' in response.text


def test_single_marker_svg_out_of_range_id_rejected(client: TestClient) -> None:
    response = client.get("/markers/50.svg")

    assert response.status_code == 422


def test_single_marker_svg_non_positive_size_rejected(client: TestClient) -> None:
    response = client.get("/markers/0.svg", params={"size_mm": 0})

    assert response.status_code == 422


def test_default_sheet_uses_reference_layout(client: TestClient) -> None:
    response = client.get("/markers")

    assert response.status_code == 200
    for marker_id in range(8):
        assert f"/markers/{marker_id}.svg?size_mm=80.0" in response.text
    assert "id 7" in response.text
    assert "id 8" not in response.text


def test_explicit_ids_and_size_override_default(client: TestClient) -> None:
    response = client.get("/markers", params={"ids": "2,5", "size_mm": 40})

    assert response.status_code == 200
    assert "/markers/2.svg?size_mm=40.0" in response.text
    assert "/markers/5.svg?size_mm=40.0" in response.text
    assert "id 0" not in response.text


def test_sheet_states_print_at_actual_size(client: TestClient) -> None:
    response = client.get("/markers")

    assert "100%" in response.text
    assert "fit to page" in response.text.lower()


def test_sheet_rejects_invalid_id_in_list(client: TestClient) -> None:
    response = client.get("/markers", params={"ids": "0,999"})

    assert response.status_code == 422
