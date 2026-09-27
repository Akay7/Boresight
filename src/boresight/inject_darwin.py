"""Cursor injection on macOS, over Quartz event services.

As on Windows, every OS call is in one small object (`QuartzApi`) that
the backend is handed, and the backend decides only which events to
post -- so the event sequences are tested on Linux against a recording
fake.

Plain ctypes, not PyObjC: the backend needs about ten C functions from
CoreGraphics, and `pyobjc-framework-Quartz` would bring pyobjc-core and
a large compiled wrapper into a core install that is deliberately kept
light. These are C APIs, not Objective-C ones, so PyObjC's bridging
buys nothing here.
"""

from __future__ import annotations

import ctypes
from typing import Protocol

from boresight.inject import (
    DEFAULT_REL_SCALE,
    CursorBackendUnavailable,
    Rect,
)

# More than any desk will have; CGGetActiveDisplayList fills up to this.
MAX_DISPLAYS = 32

# CGEventType
kCGEventLeftMouseDown = 1
kCGEventLeftMouseUp = 2
kCGEventMouseMoved = 5
kCGEventLeftMouseDragged = 6

kCGMouseButtonLeft = 0
kCGHIDEventTap = 0

# CGEventField
kCGMouseEventClickState = 1
kCGMouseEventDeltaX = 4
kCGMouseEventDeltaY = 5

_FRAMEWORKS = "/System/Library/Frameworks"

ACCESSIBILITY_HINT = (
    "macOS has not allowed this process to post input events, and "
    "without that permission every cursor move and click would be "
    "silently dropped. Open System Settings > Privacy & Security > "
    "Accessibility and enable the app that started the server -- your "
    "terminal (Terminal, iTerm, ...) or the Python binary itself if it "
    "was started some other way -- then restart the server. macOS has "
    "been asked to show its own prompt for this too."
)


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class CGRect(ctypes.Structure):
    _fields_ = [("origin", CGPoint), ("size", CGSize)]


class QuartzApi(Protocol):
    def can_post_events(self) -> bool: ...
    def request_post_events(self) -> None: ...
    def main_display_bounds(self) -> Rect: ...
    # (display ID, bounds in global points, main) for each active display.
    def displays(self) -> list[tuple[int, Rect, bool]]: ...
    def cursor_location(self) -> tuple[float, float]: ...
    def post_mouse_event(
        self, event_type: int, x: float, y: float, fields: dict[int, int]
    ) -> None: ...


def _framework(name: str) -> ctypes.CDLL:
    return ctypes.CDLL(f"{_FRAMEWORKS}/{name}.framework/{name}")


class CoreGraphicsApi:
    """The real `QuartzApi`, over CoreGraphics and CoreFoundation."""

    def __init__(self) -> None:
        try:
            cg = _framework("CoreGraphics")
            cf = _framework("CoreFoundation")
        except OSError as exc:
            raise CursorBackendUnavailable(
                "CoreGraphics is not available (the Quartz backend requires macOS)"
            ) from exc
        cg.CGEventCreateMouseEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            CGPoint,
            ctypes.c_uint32,
        ]
        cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
        cg.CGEventSetIntegerValueField.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_int64,
        ]
        cg.CGEventSetIntegerValueField.restype = None
        cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        cg.CGEventPost.restype = None
        cg.CGEventCreate.argtypes = [ctypes.c_void_p]
        cg.CGEventCreate.restype = ctypes.c_void_p
        cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]
        cg.CGEventGetLocation.restype = CGPoint
        cg.CGMainDisplayID.argtypes = []
        cg.CGMainDisplayID.restype = ctypes.c_uint32
        cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
        cg.CGDisplayBounds.restype = CGRect
        cg.CGGetActiveDisplayList.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32),
        ]
        cg.CGGetActiveDisplayList.restype = ctypes.c_int32
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFRelease.restype = None
        self._cg = cg
        self._cf = cf

    def can_post_events(self) -> bool:
        # CGPreflightPostEventAccess is the precise question (macOS
        # 10.15+). Before it, posting was gated by the Accessibility
        # trust that AXIsProcessTrusted reports.
        preflight = getattr(self._cg, "CGPreflightPostEventAccess", None)
        if preflight is not None:
            preflight.argtypes = []
            preflight.restype = ctypes.c_bool
            return bool(preflight())
        services = _framework("ApplicationServices")
        services.AXIsProcessTrusted.argtypes = []
        services.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(services.AXIsProcessTrusted())

    def request_post_events(self) -> None:
        # Shows the system prompt and adds the app to the Accessibility
        # list, switched off, so the user only has to tick it.
        request = getattr(self._cg, "CGRequestPostEventAccess", None)
        if request is not None:
            request.argtypes = []
            request.restype = ctypes.c_bool
            request()

    def main_display_bounds(self) -> Rect:
        return self._bounds(self._cg.CGMainDisplayID())

    def _bounds(self, display_id: int) -> Rect:
        bounds = self._cg.CGDisplayBounds(display_id)
        return Rect(
            bounds.origin.x, bounds.origin.y, bounds.size.width, bounds.size.height
        )

    def displays(self) -> list[tuple[int, Rect, bool]]:
        ids = (ctypes.c_uint32 * MAX_DISPLAYS)()
        count = ctypes.c_uint32(0)
        if self._cg.CGGetActiveDisplayList(MAX_DISPLAYS, ids, ctypes.byref(count)):
            return []
        main = self._cg.CGMainDisplayID()
        return [
            (ids[index], self._bounds(ids[index]), ids[index] == main)
            for index in range(count.value)
        ]

    def cursor_location(self) -> tuple[float, float]:
        event = self._cg.CGEventCreate(None)
        try:
            point = self._cg.CGEventGetLocation(event)
        finally:
            self._cf.CFRelease(event)
        return (point.x, point.y)

    def post_mouse_event(
        self, event_type: int, x: float, y: float, fields: dict[int, int]
    ) -> None:
        event = self._cg.CGEventCreateMouseEvent(
            None, event_type, CGPoint(x, y), kCGMouseButtonLeft
        )
        if not event:
            return
        try:
            for field, value in fields.items():
                self._cg.CGEventSetIntegerValueField(event, field, value)
            self._cg.CGEventPost(kCGHIDEventTap, event)
        finally:
            self._cf.CFRelease(event)


class QuartzCursorBackend:
    """Moves the cursor and presses the left button with Quartz events."""

    def __init__(
        self,
        api: QuartzApi | None = None,
        target: Rect | None = None,
        rel_scale: float = DEFAULT_REL_SCALE,
    ) -> None:
        self._api = api if api is not None else CoreGraphicsApi()
        # At startup: without the permission, posting fails silently,
        # which would look like a tracking problem rather than a
        # settings one.
        if not self._api.can_post_events():
            self._api.request_post_events()
            raise CursorBackendUnavailable(ACCESSIBILITY_HINT)
        # Global display coordinates, in points: the main display's
        # top-left is the origin, and others sit at their arranged
        # offsets, negative ones included.
        self._target = target if target is not None else self._api.main_display_bounds()
        self._rel_scale = rel_scale
        self._last_position: tuple[float, float] | None = None
        # Where the last event put the cursor, in global points; a
        # press or release is posted there.
        self._location: tuple[float, float] | None = None
        self._held = False

    def displays(self) -> list:
        from boresight.displays import Display

        # macOS has no output names; the display ID is stable while the
        # display stays connected, which is what a choice needs.
        return [
            Display(str(display_id), rect, main)
            for display_id, rect, main in self._api.displays()
        ]

    def show_on(self, display) -> None:
        self._target = display.rect

    @property
    def rel_scale(self) -> float:
        return self._rel_scale

    @rel_scale.setter
    def rel_scale(self, value: float) -> None:
        # A live setting, as on `UInputCursorBackend.rel_scale`.
        self._rel_scale = value

    def move_absolute(self, x: float, y: float) -> None:
        fields: dict[int, int] = {}
        # For a title reading raw mouse deltas; see `DEFAULT_REL_SCALE`
        # in inject.py before enabling it. Carried on the move event
        # itself, which is where macOS reports a real mouse's motion.
        if self._last_position is not None and self._rel_scale:
            last_x, last_y = self._last_position
            rel_x = round((x - last_x) * self._rel_scale)
            rel_y = round((y - last_y) * self._rel_scale)
            if rel_x or rel_y:
                fields = {kCGMouseEventDeltaX: rel_x, kCGMouseEventDeltaY: rel_y}
        location = self._target.point(x, y)
        # A plain move while the button is down is not a drag to macOS
        # applications: they only see one from the dragged event type.
        event_type = kCGEventLeftMouseDragged if self._held else kCGEventMouseMoved
        self._api.post_mouse_event(event_type, *location, fields)
        self._last_position = (x, y)
        self._location = location

    def _button(self, event_type: int) -> None:
        if self._location is None:
            # Nothing placed the cursor yet, so press where it is.
            self._location = self._api.cursor_location()
        # Click state 1: a single click. Some applications ignore a
        # button event whose click count is left at zero.
        self._api.post_mouse_event(
            event_type, *self._location, {kCGMouseEventClickState: 1}
        )

    def click(self) -> None:
        self.press()
        self.release()

    def press(self) -> None:
        self._button(kCGEventLeftMouseDown)
        self._held = True

    def release(self) -> None:
        self._button(kCGEventLeftMouseUp)
        self._held = False

    def close(self) -> None:
        if self._held:
            self.release()
