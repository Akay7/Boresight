"""Which pins the buttons and LED may use, and when a button counts as pressed.

Pure logic with no GPIO import, so the rules are tested on any machine.
"""

from __future__ import annotations

# The 26 GPIOs on the 40-pin header. 0 and 1 are the HAT ID EEPROM's I2C
# and are not on the header's general-purpose pins.
HEADER_GPIOS = frozenset(range(2, 28))


class PinError(ValueError):
    pass


def validate_pins(trigger: int, led: int | None) -> None:
    """Raises `PinError` naming the pin, before anything is presented to
    the host."""
    for name, pin in (("trigger", trigger), ("status LED", led)):
        if pin is not None and pin not in HEADER_GPIOS:
            raise PinError(
                f"{name} GPIO {pin} is not a GPIO on the 40-pin header "
                f"(valid: {min(HEADER_GPIOS)}-{max(HEADER_GPIOS)})"
            )
    if led is not None and led == trigger:
        raise PinError(f"trigger and status LED are both on GPIO {trigger}")


class Debouncer:
    """A level counts once it has held for `debounce_ms`.

    `update` takes the raw level and a time and returns the new debounced
    level when it changes, else None. Contact bounce on either edge
    therefore yields exactly one change.
    """

    def __init__(self, debounce_ms: float) -> None:
        self._debounce_ms = debounce_ms
        self._stable = False
        self._candidate = False
        self._since_ms = 0.0

    @property
    def pressed(self) -> bool:
        return self._stable

    def update(self, raw: bool, now_ms: float) -> bool | None:
        if raw != self._candidate:
            self._candidate = raw
            self._since_ms = now_ms
            return None
        if raw != self._stable and now_ms - self._since_ms >= self._debounce_ms:
            self._stable = raw
            return raw
        return None
