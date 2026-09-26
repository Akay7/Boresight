import re

import cv2
import numpy as np
import pytest

from boresight.detect import detect_markers
from boresight.markers import (
    A4_PRINTABLE_HEIGHT_MM,
    cutout_height_mm,
    fits_a4,
    marker_grid,
    marker_svg,
    paginate,
    quiet_zone_mm,
)


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


# --- Quiet zone and pagination -----------------------------------------


def test_quiet_zone_is_one_cell_of_the_grid() -> None:
    # DICT_4X4_50: 4 payload bits plus a black border cell on each side.
    assert quiet_zone_mm(80) == pytest.approx(80 / 6)
    assert quiet_zone_mm(60) == pytest.approx(10)


@pytest.mark.parametrize("marker_id", range(8))
def test_a_one_cell_white_margin_is_enough_to_detect_the_tag(marker_id: int) -> None:
    """Exactly the sheet's quiet zone -- one cell of white -- and then the
    bezel: a dark surround right where the paper is cut."""
    cell_px = 8
    grid = marker_grid(marker_id)
    side = grid.shape[0] * cell_px
    tag = cv2.resize(grid, (side, side), interpolation=cv2.INTER_NEAREST)
    cutout = np.pad(tag, cell_px, constant_values=255)
    for surround in (0, 60, 128):
        frame = np.pad(cutout, 100, constant_values=surround)
        found = detect_markers(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))

        assert [marker.marker_id for marker in found] == [marker_id]


def test_cutout_height_counts_quiet_zone_and_label_bands() -> None:
    # 80 + 2 x 13.33 of quiet zone, 6mm TOP band, two 5mm label bands,
    # 1mm padding top and bottom.
    assert cutout_height_mm(80) == pytest.approx(80 + 160 / 6 + 18)


def test_two_reference_tags_pair_on_one_a4_page() -> None:
    assert paginate([80.0] * 8) == [[0, 1], [2, 3], [4, 5], [6, 7]]


def test_an_odd_count_leaves_the_last_page_single() -> None:
    assert paginate([80.0] * 3) == [[0, 1], [2]]


def test_a_tag_too_big_to_pair_gets_its_own_page() -> None:
    assert 2 * cutout_height_mm(100) > A4_PRINTABLE_HEIGHT_MM
    assert paginate([100.0, 100.0, 100.0]) == [[0], [1], [2]]


def test_mixed_sizes_pair_only_where_both_fit() -> None:
    # 140 is too tall to share a page even with a 50; the 50s after it pair.
    assert paginate([50.0, 140.0, 50.0, 50.0]) == [[0], [1], [2, 3]]


def test_never_more_than_two_to_a_page() -> None:
    assert paginate([30.0] * 5) == [[0, 1], [2, 3], [4]]


def test_fits_a4_uses_the_one_cell_margin() -> None:
    # 190mm printable: tag x 8/6 must fit, so 142.5mm is the limit.
    assert fits_a4(120)
    assert fits_a4(142.5)
    assert not fits_a4(143)
