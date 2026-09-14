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

from boresight.overlay.backend import (
    check_supported,
    detect_environment,
    require_toolkit,
)
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


def emit_geometry(
    screen_px: tuple[int, int],
    tag_px: int,
    inset_px: int,
    area_px: tuple[int, int, int, int],
) -> None:
    print(
        json.dumps(
            {
                "event": GEOMETRY_EVENT,
                "screen_px": [screen_px[0], screen_px[1]],
                "area_px": list(area_px),
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


def _area_px(geometry, available, extra_margin_px: int) -> tuple[int, int, int, int]:
    """The usable area, in screen-local pixels, after an optional manual
    margin is subtracted from Qt's own `availableGeometry()`.

    Pure geometry, factored out so `extra_margin_px`'s effect is
    testable without a `QApplication` -- `QRect` needs no display to
    construct, only to obtain from a real screen.
    """
    if extra_margin_px:
        available = available.adjusted(
            extra_margin_px, extra_margin_px, -extra_margin_px, -extra_margin_px
        )
    return (
        available.x() - geometry.x(),
        available.y() - geometry.y(),
        available.width(),
        available.height(),
    )


def run(
    screen_index: int | None = None,
    tag_px: int | None = None,
    inset_px: int | None = None,
    report_only: bool = False,
    extra_margin_px: int = 0,
) -> int:
    """Show the overlay and run the Qt event loop until interrupted.

    `screen_index` of None means the primary display, which is what a
    single-monitor machine wants and what a multi-monitor one most
    likely wants.

    `report_only` reports the geometry that would be used and exits
    without mapping a window -- enough for a parent to learn the display
    size, and useful for exercising the handshake without putting tags
    on someone's screen.

    `extra_margin_px` shrinks the auto-detected available area by that
    amount on every side, on top of whatever Qt itself already
    subtracted. It exists because Qt's panel detection reads X11's
    `_NET_WORKAREA`, which is one rectangle for the whole virtual
    desktop rather than one per monitor -- confirmed, on a real
    multi-monitor setup, to report zero reservation for a monitor with
    a visibly occupied taskbar. Left at zero, this changes nothing.
    """
    check_supported()
    _force_xwayland_on_wayland()
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

    # The available area excludes whatever the desktop reserves for
    # panels and docks. A KDE panel takes 46px off the bottom, and a tag
    # drawn under it is invisible to the camera -- the panel is painted
    # above even an always-on-top window, and fighting it would break
    # the panel rather than fix the tag.
    available = screen.availableGeometry()
    area_px = _area_px(geometry, available, extra_margin_px)
    area_size = (area_px[2], area_px[3])

    # Resolved here rather than left to the renderer, because the
    # numbers have to be reported before anything is drawn.
    tag_px = default_tag_px(area_size) if tag_px is None else tag_px
    inset_px = default_inset_px(tag_px) if inset_px is None else inset_px

    if report_only:
        emit_geometry(screen_px, tag_px, inset_px, area_px)
        return 0

    widget = build_overlay_widget(
        area_size,
        tag_px,
        inset_px,
        QtCore=QtCore,
        QtGui=QtGui,
        QtWidgets=QtWidgets,
    )
    widget.setGeometry(available)
    widget.show()
    _install_interrupt_handler(app, widget, QtCore)

    emit_geometry(screen_px, tag_px, inset_px, area_px)
    reserved = (screen_px[1] - area_px[3]) + (screen_px[0] - area_px[2])
    print(
        f"Overlay running on {screen_px[0]}x{screen_px[1]}"
        + (f" ({reserved}px reserved by desktop panels)" if reserved else "")
        + ". Press Ctrl-C here to stop.",
        file=sys.stderr,
        flush=True,
    )
    return app.exec()


def _force_xwayland_on_wayland() -> None:
    """Make Qt speak X11 even on a Wayland desktop.

    Wayland denies an ordinary client the two things this overlay is:
    a window that stays above the others, and one that puts itself
    where it is told. As a native Wayland client the overlay comes out
    centred on the screen and drops behind whatever is clicked --
    observed on KDE Plasma, and mistakable for a Boresight bug.

    Through XWayland the same window is managed by KWin as an X11
    client, which does honour `_NET_WM_STATE_ABOVE` and absolute
    geometry. Verified: the resulting window carries
    `_NET_WM_STATE_ABOVE, _NET_WM_STATE_STAYS_ON_TOP`.

    `setdefault`, so an explicit QT_QPA_PLATFORM still wins -- the test
    suite sets `offscreen`, and anyone with a reason to choose is not
    overruled. This has to run before QApplication is constructed,
    which is when the platform plugin is loaded.
    """
    import os

    if detect_environment().is_wayland:
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")


def _install_interrupt_handler(app, widget, QtCore) -> None:
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

    The handler hides the widget and pumps events before quitting rather
    than leaving that to process teardown. Observed on KWin/XWayland: an
    always-on-top, input-transparent window that vanishes because the
    process died, instead of being unmapped while still live, can leave
    the compositor's input routing for whatever was underneath confused
    -- other windows stay unresponsive to clicks until something forces
    a restacking (e.g. hiding and reshowing one). An explicit hide gives
    the compositor a normal UnmapNotify to react to first.
    """
    import signal

    def stop(_signum, _frame) -> None:
        widget.hide()
        app.processEvents()
        app.quit()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    heartbeat = QtCore.QTimer()
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(200)
    # Outlive this function: a garbage-collected timer stops firing, and
    # Ctrl-C would go back to being ignored.
    app._boresight_heartbeat = heartbeat
