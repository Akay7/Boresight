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
    assert response.text.count("<svg") == 8
    assert "id 7" in response.text
    assert "id 8" not in response.text


def test_explicit_ids_and_size_override_default(client: TestClient) -> None:
    response = client.get("/markers", params={"ids": "2,5", "size_mm": 40})

    assert response.status_code == 200
    assert response.text.count("<svg") == 2
    assert response.text.count('width="40.0mm"') == 2
    assert "id 2" in response.text
    assert "id 0" not in response.text


def test_sheet_states_print_at_actual_size(client: TestClient) -> None:
    response = client.get("/markers")

    assert "100%" in response.text
    assert "fit to page" in response.text.lower()


def test_sheet_rejects_invalid_id_in_list(client: TestClient) -> None:
    response = client.get("/markers", params={"ids": "0,999"})

    assert response.status_code == 422


# --- Attachment guidance ---------------------------------------------


def test_the_sheet_inlines_its_tags_rather_than_linking_them(
    client: TestClient,
) -> None:
    """Not a style preference. A browser fetching an <img src> sends no
    token, so on a token-guarded server every tag on the printed sheet
    would come back 401 and you would print a page of broken images."""
    response = client.get("/markers")

    assert "<img" not in response.text
    assert "<svg" in response.text


def test_every_tag_carries_its_position(client: TestClient) -> None:
    """IDs are positions, not decoration -- swapping two produces a
    wrong aim point with no error to warn you, since a permuted
    correspondence set still fits a homography."""
    response = client.get("/markers").text

    for label in (
        "top-left corner",
        "top-right corner",
        "bottom-right corner",
        "bottom-left corner",
        "top edge, middle",
        "right edge, middle",
        "bottom edge, middle",
        "left edge, middle",
    ):
        assert label in response, f"sheet does not say where a tag goes: {label}"


def test_every_tag_carries_an_orientation_mark(client: TestClient) -> None:
    """A tag stuck on sideways is still recognised -- the detector reads
    rotation from the bit pattern -- but its corners then pair with the
    wrong screen coordinates."""
    response = client.get("/markers").text

    assert response.count('class="up"') == 8
    assert "&#9650; TOP" in response


def test_the_sheet_explains_cutting_outside_the_quiet_zone(
    client: TestClient,
) -> None:
    response = client.get("/markers").text

    assert "dashed line" in response
    assert "quiet zone" in response


def test_the_sheet_diagrams_the_layout(client: TestClient) -> None:
    response = client.get("/markers").text

    assert 'class="diagram"' in response
    assert "1220 &times; 686 mm" in response


def test_an_id_outside_the_layout_still_prints_without_a_position(
    client: TestClient,
) -> None:
    """Extra tags are legitimate -- an inner ring for close play, say --
    and must not fail the sheet just because the shipped reference
    layout does not mention them."""
    response = client.get("/markers", params={"ids": "0,42"})

    assert response.status_code == 200
    assert "id 42" in response.text
    assert response.text.count('class="up"') == 2
    # Only the mapped one gets a position.
    assert response.text.count('class="where"') == 1
