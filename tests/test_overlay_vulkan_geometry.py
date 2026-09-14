"""The Vulkan backend's rectangle geometry must match the window overlay's.

Both backends are handed the same `render_overlay` output -- the Qt
widget uses it in-process, the `.bsov` canvas is what the Vulkan layer
reads -- but they get there through separate code paths (a widget
constructor here, a file writer there). This test is the guard the
design's "same layout as the window overlay" requirement asks for: it
pins both paths down to producing identical rectangles for the same
input, so a future change that lets them drift (say, a backend growing
its own layout math instead of calling `render_overlay`) fails loudly
here rather than as a marker that decodes on one substrate and not the
other.

Skipped entirely unless the overlay extra is installed, exactly like
`test_overlay_qt.py` -- this is a cross-check between two backends, not
a reason to make the Qt extra mandatory for the Vulkan one.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6", reason="overlay extra not installed")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from boresight.overlay import canvas_format, vulkan_backend  # noqa: E402
from boresight.overlay.backend import require_toolkit  # noqa: E402
from boresight.overlay.qt_backend import build_overlay_widget  # noqa: E402

SCREENS = [(1920, 1080), (1280, 720), (2560, 1440)]


@pytest.fixture(scope="module")
def toolkit():
    return require_toolkit()


@pytest.fixture(scope="module")
def qt_app(toolkit):
    _QtCore, _QtGui, QtWidgets = toolkit
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.mark.parametrize("screen", SCREENS)
def test_vulkan_canvas_rectangles_match_the_qt_widgets(
    screen: tuple[int, int], toolkit, qt_app, tmp_path
) -> None:
    QtCore, QtGui, QtWidgets = toolkit
    widget = build_overlay_widget(
        screen, QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets
    )
    try:
        qt_rectangles = widget._rectangles
    finally:
        widget.deleteLater()

    canvas_path = tmp_path / "canvas.bsov"
    vulkan_backend.write_canvas(canvas_path, screen)
    _canvas, vulkan_rectangles = canvas_format.unpack(canvas_path.read_bytes())

    assert vulkan_rectangles == qt_rectangles


@pytest.mark.parametrize("screen", SCREENS)
def test_vulkan_canvas_pixels_match_the_qt_widgets_image(
    screen: tuple[int, int], toolkit, qt_app, tmp_path
) -> None:
    """Not just the rectangles: the tag content painted inside them too,
    so a marker ID at a given position cannot decode differently
    between backends."""
    import numpy as np

    QtCore, QtGui, QtWidgets = toolkit
    widget = build_overlay_widget(
        screen, QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets
    )
    try:
        qt_image = widget._image
        width, height = qt_image.width(), qt_image.height()
        qt_canvas = np.frombuffer(qt_image.constBits(), dtype=np.uint8).reshape(
            (height, qt_image.bytesPerLine())
        )[:, :width]
    finally:
        widget.deleteLater()

    canvas_path = tmp_path / "canvas.bsov"
    vulkan_backend.write_canvas(canvas_path, screen)
    vulkan_canvas, _rects = canvas_format.unpack(canvas_path.read_bytes())

    assert np.array_equal(vulkan_canvas, qt_canvas)
