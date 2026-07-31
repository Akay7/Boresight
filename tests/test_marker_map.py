"""Unit tests for the marker layout loader.

These exercise `marker_map.py` alone -- no detector, no solver, no
fixtures. The shipped `config/markers.toml` is checked separately, in
`test_layout_consistency.py`, against the rendered fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boresight.marker_map import MarkerMapError, load_marker_map, parse_marker_map

VALID_LAYOUT = """
screen_width_mm = 1220
screen_height_mm = 686

[[marker]]
id = 0
x = -120
y = -120
size_mm = 80

[[marker]]
id = 4
x = 570
y = -120
size_mm = 80
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "markers.toml"
    path.write_text(text)
    return path


def test_a_well_formed_layout_loads(tmp_path: Path) -> None:
    layout = load_marker_map(_write(tmp_path, VALID_LAYOUT))

    assert layout.screen_size_mm == (1220.0, 686.0)
    assert set(layout.markers) == {0, 4}
    assert layout.markers[4].size_mm == 80.0


def test_corners_are_clockwise_from_top_left() -> None:
    """The order is load-bearing: it has to match cv2.aruco's, so the two
    sequences can be zipped positionally into correspondences."""
    layout = parse_marker_map(
        {
            "screen_width_mm": 1220,
            "screen_height_mm": 686,
            "marker": [{"id": 0, "x": 100.0, "y": 200.0, "size_mm": 80.0}],
        }
    )

    assert layout.corners_mm(0) == [
        (100.0, 200.0),
        (180.0, 200.0),
        (180.0, 280.0),
        (100.0, 280.0),
    ]


def test_markers_may_differ_in_size() -> None:
    """A second inner ring for close play would use smaller tags. Each
    marker's corners come from its own size_mm, not a layout-wide one."""
    layout = parse_marker_map(
        {
            "screen_width_mm": 1220,
            "screen_height_mm": 686,
            "marker": [
                {"id": 0, "x": 0.0, "y": 0.0, "size_mm": 80.0},
                {"id": 1, "x": 0.0, "y": 0.0, "size_mm": 30.0},
            ],
        }
    )

    assert layout.corners_mm(0)[2] == (80.0, 80.0)
    assert layout.corners_mm(1)[2] == (30.0, 30.0)


def test_bezel_coordinates_outside_the_panel_are_accepted() -> None:
    """Every marker in the real layout is outside the active area. If the
    loader rejected out-of-range coordinates it would reject the layout
    the whole project is built around."""
    layout = parse_marker_map(
        {
            "screen_width_mm": 1220,
            "screen_height_mm": 686,
            "marker": [
                {"id": 0, "x": -120.0, "y": -120.0, "size_mm": 80.0},
                {"id": 2, "x": 1260.0, "y": 726.0, "size_mm": 80.0},
            ],
        }
    )

    assert layout.markers[0].x_mm == -120.0
    assert layout.markers[2].y_mm == 726.0


def test_unknown_marker_id_returns_none(tmp_path: Path) -> None:
    """Absence is a value, not an exception -- the pipeline skips
    unmapped detections rather than failing the frame."""
    layout = load_marker_map(_write(tmp_path, VALID_LAYOUT))

    assert layout.corners_mm(49) is None
    assert 49 not in layout.markers


def test_duplicate_marker_id_is_rejected() -> None:
    with pytest.raises(MarkerMapError, match="duplicate marker id 3"):
        parse_marker_map(
            {
                "screen_width_mm": 1220,
                "screen_height_mm": 686,
                "marker": [
                    {"id": 3, "x": 0.0, "y": 0.0, "size_mm": 80.0},
                    {"id": 3, "x": 10.0, "y": 10.0, "size_mm": 80.0},
                ],
            }
        )


@pytest.mark.parametrize("field", ["id", "x", "y", "size_mm"])
def test_missing_marker_field_is_rejected(field: str) -> None:
    entry = {"id": 0, "x": 0.0, "y": 0.0, "size_mm": 80.0}
    del entry[field]

    with pytest.raises(MarkerMapError, match=f"missing required field '{field}'"):
        parse_marker_map(
            {"screen_width_mm": 1220, "screen_height_mm": 686, "marker": [entry]}
        )


@pytest.mark.parametrize("field", ["screen_width_mm", "screen_height_mm"])
def test_missing_screen_dimension_is_rejected(field: str) -> None:
    data = {
        "screen_width_mm": 1220,
        "screen_height_mm": 686,
        "marker": [{"id": 0, "x": 0.0, "y": 0.0, "size_mm": 80.0}],
    }
    del data[field]

    with pytest.raises(MarkerMapError, match=f"missing required field '{field}'"):
        parse_marker_map(data)


@pytest.mark.parametrize("value", [0, -1220])
def test_non_positive_screen_dimension_is_rejected(value: int) -> None:
    with pytest.raises(MarkerMapError, match="screen_width_mm must be positive"):
        parse_marker_map(
            {
                "screen_width_mm": value,
                "screen_height_mm": 686,
                "marker": [{"id": 0, "x": 0.0, "y": 0.0, "size_mm": 80.0}],
            }
        )


@pytest.mark.parametrize("value", [0, -80])
def test_non_positive_marker_size_is_rejected(value: int) -> None:
    with pytest.raises(MarkerMapError, match="size_mm must be positive"):
        parse_marker_map(
            {
                "screen_width_mm": 1220,
                "screen_height_mm": 686,
                "marker": [{"id": 0, "x": 0.0, "y": 0.0, "size_mm": value}],
            }
        )


def test_layout_with_no_markers_is_rejected() -> None:
    with pytest.raises(MarkerMapError, match="declares no markers"):
        parse_marker_map({"screen_width_mm": 1220, "screen_height_mm": 686})
