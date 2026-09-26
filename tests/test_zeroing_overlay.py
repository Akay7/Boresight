"""The zeroing target: drawn by the overlay, sent to it by the server."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import numpy as np
import pytest

from boresight.inject import FakeCursorBackend
from boresight.layout_source import resolve_layout
from boresight.marker_source import MarkerSource, MarkerSourceController
from boresight.overlay.qt_backend import parse_target_command
from boresight.overlay.render import TAG_DARK, TAG_LIGHT, target_image


def test_the_target_is_an_opaque_patch_with_a_dark_centre() -> None:
    image = target_image(86)

    assert image.shape == (87, 87)
    assert image[43, 43] == TAG_DARK
    # Light patch between the marks: it hides whatever is beneath.
    assert (image == TAG_LIGHT).mean() > 0.5


@pytest.mark.parametrize(
    ("line", "parsed"),
    [
        ('{"target": [960, 540]}\n', (True, (960, 540))),
        ('{"target": null}', (True, None)),
        ("not json", (False, None)),
        ('{"target": [1.5, 2]}', (False, None)),
        ('{"target": [true, 2]}', (False, None)),
        ('{"other": 1}', (False, None)),
        ("[1, 2]", (False, None)),
    ],
)
def test_target_commands_are_parsed_strictly(line, parsed) -> None:
    assert parse_target_command(line) == parsed


def _echoing_overlay(out_path) -> callable:
    """A launcher whose 'overlay' reports geometry, then copies stdin."""
    body = (
        "import json,sys;"
        'print(json.dumps({"event":"overlay-ready","screen_px":[1920,1080],'
        '"area_px":[0,0,1920,1034],"tag_px":86,"inset_px":22}), flush=True);'
        f"out=open({str(out_path)!r},'w');"
        "[(out.write(line), out.flush()) for line in sys.stdin]"
    )

    def launch(_command, **kwargs):
        return subprocess.Popen([sys.executable, "-c", body], **kwargs)

    return launch


def _wait_for(path, text: str) -> str:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.exists() and text in (content := path.read_text()):
            return content
        time.sleep(0.02)
    raise AssertionError(f"{text!r} never reached the overlay")


def test_the_controller_sends_targets_to_the_overlay(tmp_path) -> None:
    out = tmp_path / "commands.txt"
    controller = MarkerSourceController(
        FakeCursorBackend(), resolve_layout("file"), launcher=_echoing_overlay(out)
    )
    assert controller.overlay_area is None
    assert controller.show_target((0.5, 0.5)) is False
    try:
        controller.select(MarkerSource.SCREEN)

        assert controller.overlay_area == ((1920, 1080), (0, 0, 1920, 1034))
        assert controller.show_target((0.5, 0.25)) is True
        assert controller.show_target(None) is True
        content = _wait_for(out, "null")
        assert content.splitlines() == ['{"target": [960, 270]}', '{"target": null}']
    finally:
        controller.shutdown()

    # Stopped: telling it anything is a quiet no.
    assert controller.show_target((0.5, 0.5)) is False


def test_the_qt_overlay_paints_the_target_where_asked() -> None:
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from boresight.overlay.backend import require_toolkit
    from boresight.overlay.qt_backend import build_overlay_widget

    QtCore, QtGui, QtWidgets = require_toolkit()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    widget = build_overlay_widget(
        (1920, 1080), QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets
    )
    widget.setGeometry(0, 0, 1920, 1080)
    widget.show()

    def painted() -> np.ndarray:
        app.processEvents()
        image = widget.grab().toImage()
        image = image.convertToFormat(QtGui.QImage.Format.Format_Grayscale8)
        pixels = np.frombuffer(image.constBits().tobytes(), np.uint8)
        return pixels.reshape(image.height(), image.bytesPerLine())[:, : image.width()]

    before = painted()
    widget.set_target((600, 400))
    shown = painted()
    widget.set_target(None)
    hidden = painted()
    widget.deleteLater()

    # Centre dot dark, light patch around it, nothing there otherwise.
    assert shown[400, 600] == TAG_DARK
    assert shown[400 + 7, 600 + 7] == TAG_LIGHT
    assert np.array_equal(hidden, before)
    # Still declines input with a target up.
    assert widget.testAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
