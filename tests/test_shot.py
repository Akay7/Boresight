"""`AimHistory` and `TriggerQueue`: what a named shot fires at, and when."""

from __future__ import annotations

import math

import pytest

from boresight.shot import (
    HISTORY_MS,
    MATCH_MS,
    AimHistory,
    TriggerAction,
    TriggerQueue,
)

# --- AimHistory -----------------------------------------------------------


def test_an_exact_frame_is_found() -> None:
    history = AimHistory()
    history.record(1000.0, (0.1, 0.1))
    history.record(1050.0, (0.2, 0.2))
    history.record(1100.0, (0.3, 0.3))

    assert history.aim_at(1050.0) == (0.2, 0.2)


def test_an_unsolved_frame_stands_in_for_the_nearest_solved_one() -> None:
    history = AimHistory()
    history.record(1000.0, (0.1, 0.1))
    history.record(1050.0, None)
    history.record(1080.0, (0.3, 0.3))

    assert history.aim_at(1050.0) == (0.3, 0.3)


def test_a_dropped_frame_is_matched_to_its_processed_neighbour() -> None:
    history = AimHistory()
    history.record(1000.0, (0.1, 0.1))
    history.record(1100.0, (0.3, 0.3))  # 1050 was displaced from the slot

    assert history.covers(1050.0)
    assert history.aim_at(1050.0) in {(0.1, 0.1), (0.3, 0.3)}


def test_nothing_close_enough_is_no_aim() -> None:
    history = AimHistory()
    history.record(1000.0, (0.1, 0.1))
    history.record(1000.0 + MATCH_MS + 50.0, None)

    assert history.aim_at(1000.0 + MATCH_MS + 50.0) is None


def test_coverage_means_the_frame_or_a_later_one_was_processed() -> None:
    history = AimHistory()
    assert not history.covers(1000.0)
    history.record(1000.0, None)

    assert history.covers(1000.0)
    assert history.covers(999.0)
    assert not history.covers(1000.5)


def test_old_entries_are_trimmed() -> None:
    history = AimHistory()
    history.record(0.0, (0.1, 0.1))
    history.record(HISTORY_MS + 10.0, (0.9, 0.9))

    assert history.aim_at(0.0, tolerance_ms=math.inf) == (0.9, 0.9)


def test_a_clock_going_backwards_starts_a_new_history() -> None:
    history = AimHistory()
    history.record(5000.0, (0.1, 0.1))
    history.record(10.0, (0.5, 0.5))

    assert history.newest_ms == 10.0
    assert history.aim_at(5000.0, tolerance_ms=math.inf) == (0.5, 0.5)


def test_a_non_finite_timestamp_is_not_recorded() -> None:
    history = AimHistory()
    history.record(math.nan, (0.1, 0.1))

    assert history.newest_ms is None


# --- TriggerQueue ---------------------------------------------------------


def test_an_unnamed_action_is_ready_at_once() -> None:
    queue = TriggerQueue()
    queue.push(TriggerAction("click"))

    assert queue.ready(AimHistory()) == [TriggerAction("click")]
    assert len(queue) == 0


def test_a_named_action_waits_for_its_frame() -> None:
    queue = TriggerQueue()
    history = AimHistory()
    queue.push(TriggerAction("down", 1050.0))

    assert queue.ready(history) == []
    history.record(1050.0, (0.2, 0.2))
    assert queue.ready(history) == [TriggerAction("down", 1050.0)]


def test_a_release_does_not_overtake_a_waiting_press() -> None:
    queue = TriggerQueue()
    history = AimHistory()
    queue.push(TriggerAction("down", 1050.0))
    queue.push(TriggerAction("up"))

    assert queue.ready(history) == []
    history.record(1050.0, (0.2, 0.2))
    assert queue.ready(history) == [
        TriggerAction("down", 1050.0),
        TriggerAction("up"),
    ]


@pytest.mark.parametrize("pending", [1, 3])
def test_forcing_takes_everything_in_order(pending: int) -> None:
    queue = TriggerQueue()
    actions = [TriggerAction("click", 9e9 + n) for n in range(pending)]
    for action in actions:
        queue.push(action)

    assert queue.ready(AimHistory(), force=True) == actions
