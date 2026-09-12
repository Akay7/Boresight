"""The Qt overlay widget itself.

Skipped entirely unless the overlay extra is installed, which it is not
on a default install -- so this file must never be the reason a suite
goes red for someone using printed markers.

Runs against Qt's offscreen platform: a real window is never mapped, so
these do not fight the developer's desktop for the top of the stacking
order. What they cannot check is the part that only a window manager
can answer -- that the surface really is above everything and really
does pass input through. That is what the manual tasks are for.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import numpy as np
import pytest

pytest.importorskip("PySide6", reason="overlay extra not installed")

# Must be set before any QApplication exists.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from boresight.detect import detect_markers  # noqa: E402
from boresight.overlay.backend import require_toolkit  # noqa: E402
from boresight.overlay.layout import (  # noqa: E402
    default_inset_px,
    default_tag_px,
    tag_positions_px,
)
from boresight.overlay.qt_backend import build_overlay_widget  # noqa: E402
from boresight.overlay.render import render_overlay  # noqa: E402

SCREEN = (1920, 1080)


@pytest.fixture(scope="module")
def toolkit():
    return require_toolkit()


@pytest.fixture(scope="module")
def qt_app(toolkit):
    _QtCore, _QtGui, QtWidgets = toolkit
    # QApplication is a singleton; reuse whatever exists.
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def widget(toolkit, qt_app):
    QtCore, QtGui, QtWidgets = toolkit
    made = build_overlay_widget(SCREEN, QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets)
    made.setGeometry(0, 0, *SCREEN)
    yield made
    made.deleteLater()


def test_the_window_declines_input(widget, toolkit) -> None:
    """The load-bearing flag. Qt maps it to an empty XShape input region
    on X11 and to WS_EX_TRANSPARENT on Windows. Without it the overlay
    would swallow the clicks Boresight injects at the aim point, and the
    gun would be shooting its own overlay."""
    QtCore, _QtGui, _QtWidgets = toolkit

    assert widget.windowFlags() & QtCore.Qt.WindowType.WindowTransparentForInput
    assert widget.testAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_the_window_takes_no_focus(widget, toolkit) -> None:
    """Keyboard input must keep reaching whatever the player is actually
    using."""
    QtCore, _QtGui, _QtWidgets = toolkit

    assert widget.focusPolicy() == QtCore.Qt.FocusPolicy.NoFocus
    assert widget.testAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_the_window_is_undecorated_and_on_top(widget, toolkit) -> None:
    QtCore, _QtGui, _QtWidgets = toolkit
    flags = widget.windowFlags()

    assert flags & QtCore.Qt.WindowType.FramelessWindowHint
    assert flags & QtCore.Qt.WindowType.WindowStaysOnTopHint


def test_the_background_is_translucent(widget, toolkit) -> None:
    """Only the tag patches are painted; the rest of the picture has to
    show through, or the overlay would black out the display."""
    QtCore, _QtGui, _QtWidgets = toolkit

    assert widget.testAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)


def test_ctrl_c_stops_the_overlay() -> None:
    """Run in a subprocess: this needs a real event loop and a real
    signal, and must not disturb pytest's own handling of either.

    Not a nicety. Qt's event loop sits in C++ and only runs a Python
    signal handler when some event arrives -- and this window receives
    none, because it is input-transparent by design. It also takes no
    focus, ignores clicks and has no title bar. Without the idle timer
    that hands control back to Python, Ctrl-C is ignored and there is
    no way at all to remove the overlay from the screen. Verified: the
    naive version hangs until killed.
    """
    program = (
        "import os, signal, threading;"
        "from boresight.overlay import qt_backend;"
        "threading.Timer(1.5,"
        " lambda: os.kill(os.getpid(), signal.SIGINT)).start();"
        "raise SystemExit(qt_backend.run())"
    )
    environment = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}

    finished = subprocess.run(
        [sys.executable, "-c", program],
        env=environment,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert finished.returncode == 0, finished.stderr.decode()[-500:]


def test_the_overlay_says_how_to_stop_it() -> None:
    """The only way out is the terminal it was started from, so that had
    better be on screen. On stderr, because stdout is the machine
    channel carrying the geometry handshake."""
    program = (
        "import os, signal, threading;"
        "from boresight.overlay import qt_backend;"
        "threading.Timer(1.5,"
        " lambda: os.kill(os.getpid(), signal.SIGINT)).start();"
        "qt_backend.run()"
    )
    environment = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}

    finished = subprocess.run(
        [sys.executable, "-c", program],
        env=environment,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert "Ctrl-C" in finished.stderr.decode()
    # stdout carries only the machine-readable handshake.
    assert "overlay-ready" in finished.stdout.decode()
    assert "Ctrl-C" not in finished.stdout.decode()


def test_the_reported_geometry_matches_what_is_drawn() -> None:
    """The handshake is only worth anything if the numbers describe the
    tags that actually appear. A parent builds the solver's layout from
    exactly this message, so a mismatch here would put the solver's
    idea of the tags somewhere the tags are not."""
    program = (
        "from boresight.overlay import qt_backend;"
        "raise SystemExit(qt_backend.run(report_only=True))"
    )
    environment = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}

    finished = subprocess.run(
        [sys.executable, "-c", program],
        env=environment,
        capture_output=True,
        timeout=30,
        check=True,
    )
    reported = json.loads(finished.stdout.decode().strip())

    screen_px = tuple(reported["screen_px"])
    _canvas, rectangles = render_overlay(
        screen_px, reported["tag_px"], reported["inset_px"]
    )
    drawn = tag_positions_px(screen_px, reported["tag_px"], reported["inset_px"])

    assert len(rectangles) == len(drawn) == 8
    # The reported tag size is the size actually rendered, and the
    # reported inset really is the gap from the edge.
    assert drawn[0] == (reported["inset_px"], reported["inset_px"])
    assert drawn[1][0] + reported["tag_px"] == screen_px[0] - reported["inset_px"]


def test_what_qt_actually_paints_still_decodes(widget, toolkit, qt_app) -> None:
    """The end of the chain: layout -> render -> Qt paint -> pixels ->
    the real detector. Everything before this asserts on a numpy array
    that no toolkit has touched."""
    _QtCore, QtGui, _QtWidgets = toolkit
    widget.show()
    qt_app.processEvents()

    image = (
        widget.grab().toImage().convertToFormat(QtGui.QImage.Format.Format_Grayscale8)
    )
    painted = np.frombuffer(image.constBits().tobytes(), np.uint8)
    painted = painted.reshape(image.height(), image.bytesPerLine())[:, : image.width()]

    detected = detect_markers(np.ascontiguousarray(painted))

    assert {marker.marker_id for marker in detected} == set(range(8))


def test_painted_tags_land_where_the_layout_says(widget, toolkit, qt_app) -> None:
    _QtCore, QtGui, _QtWidgets = toolkit
    widget.show()
    qt_app.processEvents()

    image = (
        widget.grab().toImage().convertToFormat(QtGui.QImage.Format.Format_Grayscale8)
    )
    painted = np.frombuffer(image.constBits().tobytes(), np.uint8)
    painted = painted.reshape(image.height(), image.bytesPerLine())[:, : image.width()]

    tag = default_tag_px(SCREEN)
    expected = tag_positions_px(SCREEN, tag, default_inset_px(tag))
    for marker in detect_markers(np.ascontiguousarray(painted)):
        want = expected[marker.marker_id]
        assert marker.corners[0][0] == pytest.approx(want[0], abs=2.0)
        assert marker.corners[0][1] == pytest.approx(want[1], abs=2.0)
