"""`qt_backend._area_px`: the manual margin, in isolation.

Pure `QRect` math -- needs the overlay's Qt extra installed to construct
the value types, but no display, no `QApplication`, and none of the
platform-detection machinery the rest of the overlay needs.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QRect  # noqa: E402

from boresight.overlay.qt_backend import _area_px  # noqa: E402


def test_a_zero_margin_reproduces_the_available_geometry_exactly() -> None:
    geometry = QRect(0, 0, 1920, 1080)
    available = QRect(0, 0, 1920, 1034)  # a 46px bottom panel already found

    assert _area_px(geometry, available, 0) == (0, 0, 1920, 1034)


def test_an_unset_default_margin_also_changes_nothing() -> None:
    geometry = QRect(0, 0, 1920, 1080)
    available = QRect(0, 0, 1920, 1080)  # nothing detected, as on the
    # affected monitor in practice

    assert _area_px(geometry, available, 0) == (0, 0, 1920, 1080)


def test_a_margin_shrinks_every_side_by_that_amount() -> None:
    geometry = QRect(0, 0, 1920, 1080)
    available = QRect(0, 0, 1920, 1080)  # Qt found no reservation

    x, y, width, height = _area_px(geometry, available, 40)

    assert (x, y) == (40, 40)
    assert (width, height) == (1920 - 80, 1080 - 80)


def test_the_margin_is_relative_to_a_non_primary_screens_own_origin() -> None:
    """A second monitor's `geometry()`/`availableGeometry()` are
    reported in global desktop coordinates; `area_px` must stay
    screen-local (matching `overlay_layout`'s convention) after a
    margin is applied too."""
    geometry = QRect(1440, 0, 1920, 1080)
    available = QRect(1440, 0, 1920, 1080)

    x, y, width, height = _area_px(geometry, available, 25)

    assert (x, y) == (25, 25)
    assert (width, height) == (1920 - 50, 1080 - 50)


def test_a_margin_composes_with_an_already_detected_reservation() -> None:
    geometry = QRect(0, 0, 1920, 1080)
    available = QRect(0, 0, 1920, 1034)  # Qt's own 46px bottom panel

    x, y, width, height = _area_px(geometry, available, 10)

    assert (x, y) == (10, 10)
    assert (width, height) == (1920 - 20, 1034 - 20)
