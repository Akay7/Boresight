import re

import pytest
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


def test_each_tag_has_exactly_one_cell_of_white_with_labels_outside_it(
    client: TestClient,
) -> None:
    """The quiet box holds the tag and nothing else; every label sits in
    the cut-out around it."""
    response = client.get("/markers").text

    quiet = re.findall(
        r'<div class="quiet" style="padding: ([0-9.]+)mm">(.*?)</div>', response
    )
    assert len(quiet) == 8
    for padding, inside in quiet:
        assert float(padding) == pytest.approx(80 / 6, abs=1e-3)
        assert inside.startswith("<svg") and inside.endswith("</svg>")
        assert "TOP" not in inside and "id " not in inside


def _pages(html: str) -> list[str]:
    return html.split('<div class="page">')[1:]


def test_the_default_sheet_prints_two_tags_to_a_page(client: TestClient) -> None:
    """Eight 80mm tags: an instructions page, then four pages of two."""
    response = client.get("/markers").text

    pages = _pages(response)
    assert len(pages) == 4
    assert [page.count("<svg") for page in pages] == [2, 2, 2, 2]
    assert "break-before: page" in response
    assert "@page { margin: 10mm; }" in response


def test_a_tag_too_big_to_pair_prints_alone(client: TestClient) -> None:
    response = client.get("/markers", params={"ids": "0,1,2", "size_mm": "120"})

    assert [page.count("<svg") for page in _pages(response.text)] == [1, 1, 1]


def test_the_steps_and_diagram_print_on_the_first_page(client: TestClient) -> None:
    response = client.get("/markers").text

    first_page = response.split('<div class="page">')[0]
    assert '<div class="steps">' in first_page
    assert 'class="diagram"' in first_page
    assert "Two tags print to a page" in first_page


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


# --- The sheet follows the layout the server runs with ---------------


def _custom_layout_client(fake_backend):
    from boresight.marker_map import parse_marker_map
    from boresight.server import create_app

    layout = parse_marker_map(
        {
            "screen_width_mm": 500,
            "screen_height_mm": 300,
            "marker": [
                # Deliberately not the reference assignment: id 3 at the
                # top-left, id 11 at the bottom-right, at their own sizes.
                {"id": 3, "x": -60, "y": -60, "size_mm": 50},
                {"id": 11, "x": 510, "y": 310, "size_mm": 35},
            ],
        }
    )
    return TestClient(
        create_app(
            backend_factory=lambda: fake_backend, marker_map_factory=lambda: layout
        )
    )


def test_the_sheet_uses_the_servers_layout_not_the_shipped_one(fake_backend) -> None:
    """A sheet labelled from the shipped file while the solver reads
    another is a silent ID swap: tags go up where the sheet says, and the
    aim is wrong with nothing to report it."""
    with _custom_layout_client(fake_backend) as client:
        response = client.get("/markers").text

    assert response.count("<svg") == 2
    assert "id 3" in response and "id 11" in response
    assert "id 0" not in response
    assert "500 &times; 300 mm" in response
    # id 3 is top-left in *this* layout; in the reference it is bottom-left.
    top_left = response.index("top-left corner")
    assert response.rindex("id 3", 0, top_left) > response.rfind("id 11", 0, top_left)
    assert "bottom-left corner" not in response


def test_each_tag_prints_at_its_layout_size(fake_backend) -> None:
    with _custom_layout_client(fake_backend) as client:
        response = client.get("/markers").text

    assert response.count('width="50.0mm"') == 1
    assert response.count('width="35.0mm"') == 1
    assert "exactly the size printed under it" in response


def test_an_explicit_size_still_overrides_the_layout(fake_backend) -> None:
    with _custom_layout_client(fake_backend) as client:
        response = client.get("/markers", params={"size_mm": 60}).text

    assert response.count('width="60.0mm"') == 2
    assert "exactly 60mm on a side" in response


# --- Choosing the tag size ---------------------------------------------


def test_the_sheet_offers_sizes_with_their_range(client: TestClient) -> None:
    response = client.get("/markers").text

    assert '<select name="size_mm">' in response
    for size in ("40", "60", "80", "100", "120"):
        assert f'<option value="{size}"' in response
    # The layout's own size is preselected and says so.
    assert '<option value="80" selected>' in response
    assert "matches the layout" in response
    assert "up to ~3.7 m" in response  # 80mm on a ~70 deg, 1280px camera


def test_the_picker_is_not_printed(client: TestClient) -> None:
    response = client.get("/markers").text

    assert '<form class="noprint picker"' in response


def test_a_size_matching_the_layout_raises_no_warning(client: TestClient) -> None:
    response = client.get("/markers", params={"size_mm": "80"}).text

    assert "mismatch" not in response.split("</style>")[1]


def test_a_size_differing_from_the_layout_warns_and_offers_a_layout(
    client: TestClient,
) -> None:
    """Printed at another size, every corner the solver places is wrong,
    and nothing reports it -- so the sheet has to."""
    response = client.get("/markers", params={"size_mm": "120"}).text

    assert '<div class="noprint mismatch">' in response
    assert "says 80mm" in response
    assert "/markers/layout.toml?size_mm=120" in response
    assert response.count('width="120.0mm"') == 8


def test_an_empty_size_means_as_the_layout_says(client: TestClient) -> None:
    response = client.get("/markers", params={"size_mm": ""})

    assert response.status_code == 200
    assert response.text.count('width="80.0mm"') == 8


def test_a_token_guarded_sheet_works_through_the_cookie_not_its_links() -> None:
    """The sheet's picker and download link used to copy the token into
    themselves, which put it back into URLs and the access log. Opening
    the sheet with the token sets the session cookie instead, and the
    plain links it renders are reachable with that alone."""
    from boresight.inject import FakeCursorBackend
    from boresight.netaccess import ServerConfig
    from boresight.server import create_app

    app = create_app(
        backend_factory=FakeCursorBackend, config=ServerConfig(token="s3cret")
    )
    with TestClient(app) as client:
        response = client.get("/markers", params={"token": "s3cret", "size_mm": "100"})
        followed = client.get("/markers/layout.toml", params={"size_mm": "100"})
        picked = client.get("/markers", params={"size_mm": "80"})

    assert "s3cret" not in response.text
    assert 'name="token"' not in response.text
    assert "/markers/layout.toml?size_mm=100" in response.text
    assert followed.status_code == 200
    assert picked.status_code == 200


@pytest.mark.parametrize("size", ["0", "-5", "nan", "inf", "big"])
def test_an_unusable_size_is_rejected(client: TestClient, size: str) -> None:
    assert client.get("/markers", params={"size_mm": size}).status_code == 422
    assert (
        client.get("/markers/layout.toml", params={"size_mm": size}).status_code == 422
    )


# --- The matching layout file --------------------------------------------


def _downloaded_layout(client: TestClient, **params):
    import tomllib

    from boresight.marker_map import parse_marker_map

    response = client.get("/markers/layout.toml", params=params)
    assert response.status_code == 200
    return response, parse_marker_map(tomllib.loads(response.text))


def test_the_layout_file_round_trips_unchanged_without_a_size(
    client: TestClient,
) -> None:
    from boresight.marker_map import load_marker_map
    from boresight.pipeline import DEFAULT_CONFIG_PATH

    response, layout = _downloaded_layout(client)

    assert layout == load_marker_map(DEFAULT_CONFIG_PATH)
    assert 'filename="markers.toml"' in response.headers["content-disposition"]


def test_a_resized_layout_keeps_each_gap_and_grows_outwards(
    client: TestClient,
) -> None:
    """Reference 80mm tags sit 40mm off the panel. At 120mm they must
    still sit 40mm off it, not creep 40mm over the display."""
    response, layout = _downloaded_layout(client, size_mm="120")
    markers = layout.markers

    assert all(marker.size_mm == 120 for marker in markers.values())
    assert layout.screen_size_mm == (1220, 686)
    # Top-left corner: its right and bottom edges stay 40mm off the panel.
    assert (markers[0].x_mm, markers[0].y_mm) == (-160, -160)
    # Bottom-right corner: its near edges were already where they belong.
    assert (markers[2].x_mm, markers[2].y_mm) == (1260, 726)
    # Top edge, middle: same centre along the edge, still 40mm above it.
    assert markers[4].x_mm + 60 == 610
    assert markers[4].y_mm + 120 == -40
    assert 'filename="markers-120mm.toml"' in response.headers["content-disposition"]
    assert response.text.startswith("# Boresight marker layout.")


def test_a_resized_layout_keeps_every_tag_in_its_slot(client: TestClient) -> None:
    from boresight.marker_map import load_marker_map
    from boresight.markers import marker_slot
    from boresight.pipeline import DEFAULT_CONFIG_PATH

    original = load_marker_map(DEFAULT_CONFIG_PATH)
    for size in ("40", "150"):
        _, resized = _downloaded_layout(client, size_mm=size)
        for marker_id, marker in original.markers.items():
            assert marker_slot(
                resized.markers[marker_id], resized.screen_size_mm
            ) == marker_slot(marker, original.screen_size_mm)


def test_charuco_svg_is_served_at_the_requested_width(client: TestClient) -> None:
    response = client.get("/markers/charuco.svg", params={"width_mm": 200})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert 'width="200mm"' in response.text


@pytest.mark.parametrize("width", [0, -10])
def test_charuco_svg_rejects_non_positive_width(client: TestClient, width) -> None:
    response = client.get("/markers/charuco.svg", params={"width_mm": width})

    assert response.status_code == 422


def test_charuco_page_embeds_the_board(client: TestClient) -> None:
    response = client.get("/markers/charuco")

    assert response.status_code == 200
    assert response.text.count("<svg") == 1
    assert "does not matter" in response.text


def test_marker_sheet_links_to_the_calibration_board(client: TestClient) -> None:
    assert 'href="/markers/charuco"' in client.get("/markers").text
