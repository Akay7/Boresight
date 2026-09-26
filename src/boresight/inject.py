"""Cursor injection backends.

Coordinates are normalized floats in [0.0, 1.0] (fraction of screen
width/height). The uinput backend maps them onto the device's absolute
axis range, 0-32767, matching the 16-bit HID absolute range Boresight's
future hardware paths also target.

The uinput backend can *optionally* also drive a relative delta
alongside its normal absolute placement, for a game that switches to
raw/relative mouse capture for camera or reticle control in fullscreen
instead of reading the OS cursor position. Off by default, and should
stay off unless `rel_scale` is set deliberately (see `settings.py`) -- see
`DEFAULT_REL_SCALE`'s comment for why continuous relative deltas are a
materially riskier feature than the absolute placement, not just an
alternative shape of the same thing.
"""

from __future__ import annotations

from typing import Protocol

from boresight.one_euro import OneEuroFilter

ABS_MAX = 32767

# Tip pressure for a click, out of the pen's 0-1023 range. Well clear of
# libinput's tip-contact threshold (a few percent of the range); any
# value above it is the same click.
CLICK_PRESSURE = 512

# Device-motion units per full [0.0, 1.0] sweep of the relative axis.
# Zero (off) by default -- deliberately, not merely a conservative
# starting point. Absolute placement is self-correcting: whatever
# noise or jitter camera-based tracking has, each frame snaps to
# wherever the aim solve currently reads, regardless of history. A
# relative delta computed frame-to-frame from that same noisy signal
# has no such correction -- it accumulates every frame's jitter as a
# random walk, which drifts without bound given enough frames and
# eventually pins against a screen or reticle edge and stays there.
# Confirmed exactly that way in practice: enabling this at a first-
# guess scale sent the cursor to a corner and left it there. A smaller
# scale only slows the drift, it does not remove it -- this is not
# presently safe to enable outside a deliberate, supervised experiment.
DEFAULT_REL_SCALE = 0.0


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
    def press(self) -> None: ...
    def release(self) -> None: ...


class CursorBackendUnavailable(RuntimeError):
    """Raised when a cursor backend cannot be initialized (e.g. no
    permission to open /dev/uinput, or the uinput kernel module is
    unavailable)."""


class UinputCursorBackend:
    """Moves the cursor via a virtual absolute pointer on Linux uinput."""

    def __init__(self, rel_scale: float = DEFAULT_REL_SCALE) -> None:
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
                'to the device (see "/dev/uinput permission" under '
                '"Running the server" in README.md for the udev rule).'
            ) from exc

        try:
            # The relative-motion device (and formerly click()'s; see
            # click() for why that moved to the pen) -- deliberately
            # separate from `self._device` above. Adding
            # BTN_LEFT to the ABS_X/Y + BTN_TOUCH + INPUT_PROP_DIRECT
            # device above changes udev's classification of it from
            # ID_INPUT_TOUCHSCREEN to ID_INPUT_MOUSE, which would send
            # move_absolute's positioning back through relative-motion
            # acceleration instead of the direct placement the touch
            # capability alone earns it.
            #
            # REL_X/REL_Y are declared here and now written on every move
            # (previously declared but unused): a title reading the OS
            # cursor position gets `self._device`'s absolute placement,
            # one reading raw/relative mouse motion for its own camera or
            # reticle gets this device's deltas instead. Motivated by a
            # real title (Blue Estate, exclusive fullscreen) that did not
            # respond to this backend's absolute-only placement there,
            # while a real mouse's relative motion worked fine in the same
            # fullscreen session -- the working theory this change acts
            # on, not yet re-confirmed in-game after the change. A button
            # with no motion axis at all was separately confirmed, against
            # a plain Xorg session (querying the X core pointer's button
            # state via Xlib before/after a write), to still land on the
            # shared core pointer -- X11 merges every pointer-capable
            # device into one core pointer regardless of which one reports
            # what. Under a Wayland compositor, though, libinput itself
            # decides per device whether BTN_LEFT means anything: without
            # a motion capability it classifies the device as a bare
            # keyboard, and the button event never reaches an application
            # as a click. REL_X/REL_Y earn it LIBINPUT_DEVICE_CAP_POINTER
            # -- the same classification a real relative mouse gets.
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
            self._relative_device = UInput(
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
        self._rel_scale = rel_scale
        # None until the first move_absolute call -- there is no prior
        # position to take a delta against yet, and emitting one against
        # an arbitrary starting point would be a spurious jump.
        self._last_position: tuple[float, float] | None = None
        self._held = False

        # Bring the pen into proximity once and leave it there for the
        # life of the backend. Proximity is what makes the cursor track
        # the reported coordinate; entering and leaving it per frame
        # would be a stream of tool-in/tool-out transitions rather than
        # simple movement.
        self._device.write(ecodes.EV_KEY, ecodes.BTN_TOOL_PEN, 1)
        self._device.write(ecodes.EV_ABS, ecodes.ABS_PRESSURE, 0)
        self._device.syn()

    @property
    def rel_scale(self) -> float:
        return self._rel_scale

    @rel_scale.setter
    def rel_scale(self, value: float) -> None:
        # A live setting (`settings.py`): set from a request thread and
        # read by whichever thread moves next. One float assignment, so
        # a move sees the old scale or the new one, nothing in between.
        self._rel_scale = value

    def move_absolute(self, x: float, y: float) -> None:
        abs_x = round(x * ABS_MAX)
        abs_y = round(y * ABS_MAX)
        # Position only. The pen is already in proximity, and this never
        # touches the tip: with the tip up it moves the cursor and
        # nothing else, and with it held down by press() it is a drag.
        self._device.write(self._ecodes.EV_ABS, self._ecodes.ABS_X, abs_x)
        self._device.write(self._ecodes.EV_ABS, self._ecodes.ABS_Y, abs_y)
        self._device.syn()

        # Alongside the absolute placement above: a relative delta from
        # the last position, for a title reading raw mouse motion
        # instead. See `self._relative_device`'s construction comment.
        if self._last_position is not None:
            last_x, last_y = self._last_position
            rel_x = round((x - last_x) * self._rel_scale)
            rel_y = round((y - last_y) * self._rel_scale)
            if rel_x or rel_y:
                self._relative_device.write(
                    self._ecodes.EV_REL, self._ecodes.REL_X, rel_x
                )
                self._relative_device.write(
                    self._ecodes.EV_REL, self._ecodes.REL_Y, rel_y
                )
                self._relative_device.syn()
        self._last_position = (x, y)

    def click(self) -> None:
        # A pen tap -- tip down, then up -- at wherever the pen is
        # hovering, which is exactly where move_absolute left the cursor.
        # A click reports that the trigger was pulled, not a new position.
        self.press()
        self.release()

    def press(self) -> None:
        # Tip down, and it stays down: every move_absolute until
        # release() drags with it.
        #
        # Not BTN_LEFT on `self._relative_device`: under a Wayland
        # compositor (seen on KWin) the tablet tool and the mouse are
        # separate pointers. The pen moves the visible cursor, but a
        # mouse button lands at the mouse pointer's own position, which
        # nothing moves while relative deltas are off -- so the trigger
        # counted on the server and clicked nowhere useful. The tip is
        # the tablet's own button, delivered at the tablet's position.
        #
        # Pressure as well as BTN_TOUCH: for a pressure-capable tool
        # libinput decides tip contact from a pressure threshold and
        # ignores BTN_TOUCH alone.
        self._device.write(
            self._ecodes.EV_ABS, self._ecodes.ABS_PRESSURE, CLICK_PRESSURE
        )
        self._device.write(self._ecodes.EV_KEY, self._ecodes.BTN_TOUCH, 1)
        self._device.syn()
        self._held = True

    def release(self) -> None:
        self._device.write(self._ecodes.EV_ABS, self._ecodes.ABS_PRESSURE, 0)
        self._device.write(self._ecodes.EV_KEY, self._ecodes.BTN_TOUCH, 0)
        self._device.syn()
        self._held = False

    def close(self) -> None:
        # Lift the tip and leave proximity before going away, so the pen
        # is neither left pressed nor left hovering from the
        # compositor's point of view.
        if self._held:
            self.release()
        self._device.write(self._ecodes.EV_KEY, self._ecodes.BTN_TOOL_PEN, 0)
        self._device.syn()
        self._device.close()
        self._relative_device.close()


class SmoothingCursorBackend:
    """Wraps another `CursorBackend`, smoothing `move_absolute` positions.

    `click()`, `press()` and `release()` pass straight through: they
    neither read the filter's state nor feed it, so a button always acts
    at wherever the wrapped backend's cursor already is -- unaffected by
    this class -- rather than at some position of its own.

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
        self._move((x, y), None)

    def at(self, t: float) -> CursorBackend:
        """This backend, with every move filtered as if made at time `t`.

        For a move that comes from a frame: the frame's capture time is
        the right `dt` source, not whenever the move happens to reach
        this object after the network and the decoder. A view per call
        rather than a settable "current time", because frames from
        different sessions are processed concurrently.
        """
        return _StampedMoves(self, t)

    def _move(self, point: tuple[float, float], t: float | None) -> None:
        smoothed_x, smoothed_y = self._filter.apply(point, t=t)
        self._backend.move_absolute(smoothed_x, smoothed_y)

    def click(self) -> None:
        self._backend.click()

    def press(self) -> None:
        self._backend.press()

    def release(self) -> None:
        self._backend.release()


class _StampedMoves:
    """A `SmoothingCursorBackend` whose moves all happen at one time."""

    def __init__(self, smoothing: SmoothingCursorBackend, t: float) -> None:
        self._smoothing = smoothing
        self._t = t

    def move_absolute(self, x: float, y: float) -> None:
        self._smoothing._move((x, y), self._t)  # noqa: SLF001 - its own view

    def click(self) -> None:
        self._smoothing.click()

    def press(self) -> None:
        self._smoothing.press()

    def release(self) -> None:
        self._smoothing.release()


def stamped(backend: CursorBackend, t: float | None) -> CursorBackend:
    """`backend`, with its moves timed at `t` where timing means anything.

    Only a smoothing backend has a use for the time; any other backend
    moves where it is told whenever it is told, so it is returned as is,
    as is every backend when there is no time to give.
    """
    if t is None or not isinstance(backend, SmoothingCursorBackend):
        return backend
    return backend.at(t)


class FakeCursorBackend:
    """Records calls instead of touching a real device. Test-only."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, float]] = []
        self.clicks: int = 0
        self.presses: int = 0
        self.releases: int = 0

    @property
    def held(self) -> bool:
        return self.presses > self.releases

    def move_absolute(self, x: float, y: float) -> None:
        self.calls.append((x, y))

    def click(self) -> None:
        self.clicks += 1

    def press(self) -> None:
        self.presses += 1

    def release(self) -> None:
        self.releases += 1


class TriggerHold:
    """The primary button, shared by every session that can hold it.

    One backend serves every connected client, so one button does too:
    it goes down when the first session holds it and up when the last
    one lets go. Each session releases only its own hold -- its `up`,
    its disconnect or its going silent never lifts a button another
    session is still holding.

    Owners are compared by identity; the server uses each session's
    stats object. Kept out of the backend itself, which has no idea
    which session a call comes from.
    """

    def __init__(self, backend: CursorBackend) -> None:
        self._backend = backend
        # id -> owner. The owner itself is kept so its id cannot be
        # reused by another object while it holds. Owners need not be
        # hashable (the server's are dataclasses).
        self._holders: dict[int, object] = {}

    @property
    def active(self) -> bool:
        return bool(self._holders)

    def holds(self, owner: object) -> bool:
        return id(owner) in self._holders

    def acquire(self, owner: object) -> bool:
        """Hold for `owner`. False if it already held."""
        if id(owner) in self._holders:
            return False
        if not self._holders:
            self._backend.press()
        self._holders[id(owner)] = owner
        return True

    def release(self, owner: object) -> bool:
        """Let go for `owner`. False if it was not holding."""
        if id(owner) not in self._holders:
            return False
        del self._holders[id(owner)]
        if not self._holders:
            self._backend.release()
        return True

    def click(self) -> None:
        # With the button already held by someone, a tap would lift it
        # under them. Down is already down, so there is nothing to add.
        if not self._holders:
            self._backend.click()
