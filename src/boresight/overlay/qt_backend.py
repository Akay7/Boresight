"""The Qt overlay window.

Imported only after `backend.check_supported` has passed and only when
the overlay extra is installed, so nothing here is reachable on a
default install.

Three flags carry the whole feature:

  FramelessWindowHint      no title bar, no decoration to click
  WindowStaysOnTopHint     above other windows
  WindowTransparentForInput  every event passes through

The last one is the load-bearing one. Qt maps it to an empty XShape
input region on X11 and to `WS_EX_TRANSPARENT` on Windows -- the
correct primitive on each. Without it the overlay would eat the clicks
Boresight injects at the aim point, and the gun would be shooting its
own overlay.
"""

from __future__ import annotations

import json
import sys

import numpy as np

from boresight.overlay.backend import check_supported, require_toolkit
from boresight.overlay.layout import default_inset_px, default_tag_px
from boresight.overlay.render import render_overlay

# Written to stdout, one line, as soon as the geometry is known. A
# parent process builds the solver's layout from exactly these numbers
# rather than assuming a resolution, which is what keeps the drawn and
# solved layouts identical.
#
# stdout is the machine channel and stderr the human one, so the banner
# and this message can change without breaking each other.
GEOMETRY_EVENT = "overlay-ready"


def emit_geometry(screen_px: tuple[int, int], tag_px: int, inset_px: int) -> None:
    print(
        json.dumps(
            {
                "event": GEOMETRY_EVENT,
                "screen_px": [screen_px[0], screen_px[1]],
                "tag_px": tag_px,
                "inset_px": inset_px,
            }
        ),
        flush=True,
    )


def _to_qimage(canvas: np.ndarray, QtGui):
    """Greyscale array -> QImage, with the buffer kept alive.

    QImage wraps the memory rather than copying it, so a bare
    `QImage(array.data, ...)` would show whatever replaced a freed
    numpy buffer. `.copy()` hands ownership to Qt.
    """
    height, width = canvas.shape
    image = QtGui.QImage(
        canvas.data, width, height, width, QtGui.QImage.Format.Format_Grayscale8
    )
    return image.copy()


def build_overlay_widget(
    screen_px, tag_px=None, inset_px=None, QtCore=None, QtGui=None, QtWidgets=None
):
    """Construct the overlay widget for a display of `screen_px`."""
    canvas, rectangles = render_overlay(screen_px, tag_px, inset_px)
    image = _to_qimage(canvas, QtGui)

    class Overlay(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowFlags(
                QtCore.Qt.WindowType.FramelessWindowHint
                | QtCore.Qt.WindowType.WindowStaysOnTopHint
                | QtCore.Qt.WindowType.WindowTransparentForInput
                | QtCore.Qt.WindowType.Tool
            )
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
            # Belt and braces: the window flag is what actually makes
            # the surface input-transparent at the platform level, and
            # this makes the widget itself decline events even if a
            # platform plugin ignores the flag.
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
            self._image = image
            self._rectangles = rectangles

        def paintEvent(self, event) -> None:  # noqa: N802 - Qt's name
            painter = QtGui.QPainter(self)
            # Only the patches are drawn. Everything else stays
            # untouched, so the overlay occludes a few percent of the
            # picture rather than covering it.
            for x, y, width, height in self._rectangles:
                painter.drawImage(x, y, self._image, x, y, width, height)
            painter.end()

    return Overlay()


def run(
    screen_index: int | None = None,
    tag_px: int | None = None,
    inset_px: int | None = None,
    report_only: bool = False,
) -> int:
    """Show the overlay and run the Qt event loop until interrupted.

    `screen_index` of None means the primary display, which is what a
    single-monitor machine wants and what a multi-monitor one most
    likely wants.

    `report_only` reports the geometry that would be used and exits
    without mapping a window -- enough for a parent to learn the display
    size, and useful for exercising the handshake without putting tags
    on someone's screen.
    """
    check_supported()
    QtCore, QtGui, QtWidgets = require_toolkit()

    app = QtWidgets.QApplication([])
    screens = app.screens()
    if screen_index is None:
        screen = app.primaryScreen()
    elif 0 <= screen_index < len(screens):
        screen = screens[screen_index]
    else:
        raise SystemExit(
            f"no display {screen_index}; this machine reports {len(screens)}"
        )
    geometry = screen.geometry()
    screen_px = (geometry.width(), geometry.height())

    # Resolved here rather than left to the renderer, because the
    # numbers have to be reported before anything is drawn.
    tag_px = default_tag_px(screen_px) if tag_px is None else tag_px
    inset_px = default_inset_px(tag_px) if inset_px is None else inset_px

    if report_only:
        emit_geometry(screen_px, tag_px, inset_px)
        return 0

    widget = build_overlay_widget(
        screen_px,
        tag_px,
        inset_px,
        QtCore=QtCore,
        QtGui=QtGui,
        QtWidgets=QtWidgets,
    )
    widget.setGeometry(geometry)
    widget.show()
    _install_interrupt_handler(app, QtCore)

    emit_geometry(screen_px, tag_px, inset_px)
    print(
        f"Overlay running on {screen_px[0]}x{screen_px[1]}. Press Ctrl-C here to stop.",
        file=sys.stderr,
        flush=True,
    )
    return app.exec()


def _install_interrupt_handler(app, QtCore) -> None:
    """Make Ctrl-C work.

    Two problems, both of which would otherwise leave an overlay nobody
    can remove. Qt's event loop sits in C++ and does not return to the
    interpreter, so a SIGINT is recorded but its Python handler never
    runs until some event happens to arrive -- and this window receives
    no events at all, because it is input-transparent by design. And
    the usual escape hatches do not apply either: the overlay takes no
    focus, ignores every click, and has no title bar to close.

    So: a handler that asks Qt to quit, plus an idle timer whose only
    job is to hand control back to Python often enough for that handler
    to be delivered.
    """
    import signal

    def stop(_signum, _frame) -> None:
        app.quit()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    heartbeat = QtCore.QTimer()
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(200)
    # Outlive this function: a garbage-collected timer stops firing, and
    # Ctrl-C would go back to being ignored.
    app._boresight_heartbeat = heartbeat
