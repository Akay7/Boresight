"""Cursor injection backends.

Coordinates are normalized floats in [0.0, 1.0] (fraction of screen
width/height). The uinput backend maps them onto the device's absolute
axis range, 0-32767, matching the 16-bit HID absolute range Boresight's
future hardware paths also target.
"""

from __future__ import annotations

from typing import Protocol

from boresight.one_euro import OneEuroFilter

ABS_MAX = 32767

# python-evdev's `UInput` defaults every device to vendor/product/version
# 1/1/1 (USB) unless told otherwise. Two Boresight devices left at that
# default present identical hardware identity to the OS -- distinct
# arbitrary product IDs are all that is needed to tell them apart; see
# the comment where each is constructed for why that turned out to
# matter here.
BORESIGHT_CURSOR_PRODUCT_ID = 0xB051
BORESIGHT_TRIGGER_PRODUCT_ID = 0xB052


class CursorBackend(Protocol):
    def move_absolute(self, x: float, y: float) -> None: ...
    def click(self) -> None: ...


class CursorBackendUnavailable(RuntimeError):
    """Raised when a cursor backend cannot be initialized (e.g. no
    permission to open /dev/uinput, or the uinput kernel module is
    unavailable)."""


class UinputCursorBackend:
    """Moves the cursor via a virtual absolute pointer on Linux uinput."""

    def __init__(self) -> None:
        try:
            from evdev import AbsInfo, UInput, ecodes
        except ImportError as exc:  # pragma: no cover - platform guard
            raise CursorBackendUnavailable(
                "evdev is not available (uinput backend requires Linux)"
            ) from exc

        # A stylus hovering over a display tablet: the cursor follows the
        # pen while it is in proximity, and only a tip-down (BTN_TOUCH)
        # is a click. That distinction is the whole reason for this
        # device type. A touchscreen -- the obvious alternative, and
        # what this backend used first -- has no hover state at all: it
        # reports a position only while a touch is active, so moving the
        # cursor meant emitting a BTN_TOUCH down/up per call, and
        # libinput turns a touchscreen tap into a pointer button
        # press/release. At frame rate that is ~20 clicks a second
        # landing wherever the aim point happens to be: windows
        # activating and minimizing, popups opening, text selecting.
        #
        # `resolution` is not decorative here: udev's input_id needs it
        # to derive a physical size, without which the device is not
        # tagged ID_INPUT_TABLET and libinput's tablet backend rejects
        # it ("missing tablet capabilities"). ABS_PRESSURE and
        # BTN_STYLUS are required for the same reason -- a stylus that
        # cannot report pressure is not a stylus as far as libinput is
        # concerned. All verified against a running X11 session.
        axis = AbsInfo(value=0, min=0, max=ABS_MAX, fuzz=0, flat=0, resolution=100)
        pressure = AbsInfo(value=0, min=0, max=1023, fuzz=0, flat=0, resolution=0)
        capabilities = {
            ecodes.EV_ABS: [
                (ecodes.ABS_X, axis),
                (ecodes.ABS_Y, axis),
                (ecodes.ABS_PRESSURE, pressure),
            ],
            ecodes.EV_KEY: [
                ecodes.BTN_TOOL_PEN,
                ecodes.BTN_TOUCH,
                ecodes.BTN_STYLUS,
            ],
        }
        try:
            # INPUT_PROP_DIRECT means a *display* tablet, whose surface
            # maps onto the screen -- so a reported coordinate is a
            # screen coordinate. Without it the device is an opaque
            # drawing tablet and libinput is free to map it differently.
            self._device = UInput(
                capabilities,
                name="boresight-cursor",
                input_props=[ecodes.INPUT_PROP_DIRECT],
                product=BORESIGHT_CURSOR_PRODUCT_ID,
            )
        except OSError as exc:
            raise CursorBackendUnavailable(
                "Could not open /dev/uinput. Check that the uinput kernel "
                "module is loaded and this process has read/write access "
                "to the device (see the change's setup notes for the "
                "udev rule)."
            ) from exc

        try:
            # click()'s own device, deliberately separate from the one
            # above. Adding BTN_LEFT to the ABS_X/Y + BTN_TOUCH +
            # INPUT_PROP_DIRECT device above changes udev's
            # classification of it from ID_INPUT_TOUCHSCREEN to
            # ID_INPUT_MOUSE, which would send move_absolute's
            # positioning back through relative-motion acceleration
            # instead of the direct placement the touch capability
            # alone earns it.
            #
            # REL_X/REL_Y are declared here but never written to. A
            # button with no motion axis at all was confirmed against a
            # plain Xorg session (querying the X core pointer's button
            # state via Xlib before/after a write) to still land on the
            # shared core pointer -- X11 merges every pointer-capable
            # device into one core pointer regardless of which one
            # reports what. Under a Wayland compositor, though, libinput
            # itself decides per device whether BTN_LEFT means anything:
            # without a motion capability it classifies the device as a
            # bare keyboard, and the button event never reaches an
            # application as a click. REL_X/REL_Y earn it
            # LIBINPUT_DEVICE_CAP_POINTER -- the same classification a
            # real relative mouse gets, at the cost of it also having a
            # (silent, unused) capability for exactly the motion this
            # device is not meant to move the cursor with.
            #
            # `product=` also matters here, separately from the name:
            # python-evdev's `UInput` defaults every device to the same
            # vendor/product/version/bustype (1/1/1/USB) unless told
            # otherwise, so this device and the one above were
            # presenting *identical* hardware identity in
            # /proc/bus/input/devices -- confirmed to coincide with
            # KWin's XWayland logging "[dix] couldn't enable device"
            # for new input devices on every server start (`journalctl
            # --user`), a known category of X input bug when device
            # identity collides. Giving each device its own product ID
            # is a one-line difference with no other effect.
            self._click_device = UInput(
                {
                    ecodes.EV_KEY: [ecodes.BTN_LEFT],
                    ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y],
                },
                name="boresight-trigger",
                product=BORESIGHT_TRIGGER_PRODUCT_ID,
            )
        except OSError as exc:
            self._device.close()
            raise CursorBackendUnavailable(
                "Could not open /dev/uinput for the trigger device."
            ) from exc

        self._ecodes = ecodes

        # Bring the pen into proximity once and leave it there for the
        # life of the backend. Proximity is what makes the cursor track
        # the reported coordinate; entering and leaving it per frame
        # would be a stream of tool-in/tool-out transitions rather than
        # simple movement.
        self._device.write(ecodes.EV_KEY, ecodes.BTN_TOOL_PEN, 1)
        self._device.write(ecodes.EV_ABS, ecodes.ABS_PRESSURE, 0)
        self._device.syn()

    def move_absolute(self, x: float, y: float) -> None:
        abs_x = round(x * ABS_MAX)
        abs_y = round(y * ABS_MAX)
        # Position only. The pen is already in proximity and its tip
        # never goes down, so this moves the cursor and nothing else --
        # no BTN_TOUCH, and therefore no click.
        self._device.write(self._ecodes.EV_ABS, self._ecodes.ABS_X, abs_x)
        self._device.write(self._ecodes.EV_ABS, self._ecodes.ABS_Y, abs_y)
        self._device.syn()

    def click(self) -> None:
        # BTN_LEFT press then release, on the dedicated click device, at
        # whatever position the last move_absolute call left the
        # cursor -- a click reports that the trigger was pulled, not a
        # new position.
        self._click_device.write(self._ecodes.EV_KEY, self._ecodes.BTN_LEFT, 1)
        self._click_device.syn()
        self._click_device.write(self._ecodes.EV_KEY, self._ecodes.BTN_LEFT, 0)
        self._click_device.syn()

    def close(self) -> None:
        # Leave proximity before going away, so the pen is not left
        # hovering from the compositor's point of view.
        self._device.write(self._ecodes.EV_KEY, self._ecodes.BTN_TOOL_PEN, 0)
        self._device.syn()
        self._device.close()
        self._click_device.close()


class SmoothingCursorBackend:
    """Wraps another `CursorBackend`, smoothing `move_absolute` positions.

    `click()` passes straight through: it neither reads the filter's
    state nor feeds it, so a click always fires at wherever the wrapped
    backend's cursor already is -- unaffected by this class -- rather
    than at some position of its own.

    Composes at the `CursorBackend` seam rather than living inside
    `AimPipeline`, so the pipeline stays exactly as stateless as its own
    spec requires; see `add-aim-smoothing`'s design for why.
    """

    def __init__(
        self, backend: CursorBackend, filter: OneEuroFilter | None = None
    ) -> None:
        self._backend = backend
        self._filter = filter if filter is not None else OneEuroFilter()

    def move_absolute(self, x: float, y: float) -> None:
        smoothed_x, smoothed_y = self._filter.apply((x, y))
        self._backend.move_absolute(smoothed_x, smoothed_y)

    def click(self) -> None:
        self._backend.click()


class FakeCursorBackend:
    """Records calls instead of touching a real device. Test-only."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, float]] = []
        self.clicks: int = 0

    def move_absolute(self, x: float, y: float) -> None:
        self.calls.append((x, y))

    def click(self) -> None:
        self.clicks += 1
