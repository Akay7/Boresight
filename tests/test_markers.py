import re

import pytest

from boresight.markers import marker_grid, marker_svg


def test_grid_is_6x6_for_dict_4x4_50() -> None:
    grid = marker_grid(0)

    assert grid.shape == (6, 6)


def test_grid_out_of_range_id_raises() -> None:
    with pytest.raises(ValueError):
        marker_grid(-1)

    with pytest.raises(ValueError):
        marker_grid(50)


def test_svg_dimensions_match_requested_size_mm() -> None:
    svg = marker_svg(0, 42.5)

    assert 'width="42.5mm"' in svg
    assert 'height="42.5mm"' in svg


def test_svg_encodes_one_rect_per_black_cell() -> None:
    grid = marker_grid(0)
    svg = marker_svg(0, 80)

    expected_black_cells = int((grid == 0).sum())
    assert len(re.findall(r"<rect x=", svg)) - 1 == expected_black_cells


def test_svg_invalid_id_raises() -> None:
    with pytest.raises(ValueError):
        marker_svg(999, 80)


def test_svg_non_positive_size_raises() -> None:
    with pytest.raises(ValueError):
        marker_svg(0, 0)

    with pytest.raises(ValueError):
        marker_svg(0, -10)
