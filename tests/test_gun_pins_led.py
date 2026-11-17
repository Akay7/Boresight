"""Pin rules, the debouncer, the LED patterns and the capture-time rule."""

from __future__ import annotations

import pytest

from boresight.gun.led import PATTERNS, State, StatusIndicator, level_at
from boresight.gun.pins import Debouncer, PinError, validate_pins
from boresight.gun.timing import capture_time


@pytest.mark.parametrize("trigger", [2, 17, 27])
def test_a_free_header_gpio_is_accepted(trigger) -> None:
    validate_pins(trigger, None)
    validate_pins(trigger, 22)


@pytest.mark.parametrize(
    ("trigger", "led", "message"),
    [
        (17, 17, "both on GPIO 17"),
        (0, 27, "trigger GPIO 0"),
        (28, None, "trigger GPIO 28"),
        (17, 99, "status LED GPIO 99"),
        (-1, None, "trigger GPIO -1"),
    ],
)
def test_an_invalid_pin_is_refused_and_named(trigger, led, message) -> None:
    with pytest.raises(PinError, match=message):
        validate_pins(trigger, led)


def _feed(debouncer: Debouncer, samples: list[tuple[bool, float]]) -> list[bool]:
    return [c for raw, t in samples if (c := debouncer.update(raw, t)) is not None]


def test_a_press_with_bounce_is_one_down_and_one_up() -> None:
    debouncer = Debouncer(10)
    samples = []
    # Bounce on the way down, steady, bounce on the way up, steady.
    for t, raw in enumerate([1, 0, 1, 0, 1, 1, 1, 1], start=0):
        samples.append((bool(raw), t * 2.0))
    samples += [(True, 20.0 + t) for t in range(0, 40, 2)]
    for t, raw in enumerate([0, 1, 0, 1, 0, 0, 0, 0]):
        samples.append((bool(raw), 100.0 + t * 2.0))
    samples += [(False, 120.0 + t) for t in range(0, 40, 2)]

    assert _feed(debouncer, samples) == [True, False]


def test_a_glitch_shorter_than_the_debounce_is_ignored() -> None:
    debouncer = Debouncer(10)

    changes = _feed(debouncer, [(False, 0), (True, 2), (False, 4), (False, 30)])

    assert changes == []
    assert debouncer.pressed is False


def test_the_aiming_to_searching_switch_changes_the_pattern() -> None:
    assert PATTERNS[State.AIMING] != PATTERNS[State.SEARCHING]
    aiming = {level_at(State.AIMING, t) for t in range(0, 2000, 50)}
    searching = {level_at(State.SEARCHING, t) for t in range(0, 2000, 50)}
    assert aiming == {True}
    assert searching == {True, False}


def test_every_state_has_a_distinct_pattern() -> None:
    assert len(set(PATTERNS.values())) == len(State)


def test_with_no_led_state_changes_are_logged() -> None:
    lines: list[str] = []
    indicator = StatusIndicator(None, log=lines.append)

    indicator.set_state(State.AIMING)
    indicator.set_state(State.AIMING)  # no change, no line
    indicator.set_state(State.SEARCHING)
    indicator.start()  # nothing to drive
    indicator.stop()

    assert lines == ["status: aiming", "status: searching"]


def test_the_sensor_timestamp_is_used_when_plausible() -> None:
    assert capture_time(9.95, 10.0) == 9.95


@pytest.mark.parametrize("sensor", [None, 0.0, 12.0, 5.0])
def test_an_implausible_sensor_timestamp_falls_back_to_now(sensor) -> None:
    assert capture_time(sensor, 10.0) == 10.0
