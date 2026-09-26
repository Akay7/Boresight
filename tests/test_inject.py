from boresight.inject import (
    FakeCursorBackend,
    SmoothingCursorBackend,
    TriggerHold,
    stamped,
)
from boresight.one_euro import OneEuroFilter


def test_click_is_recorded_without_a_real_device() -> None:
    backend = FakeCursorBackend()

    backend.click()

    assert backend.clicks == 1


def test_repeated_clicks_each_increment_the_count() -> None:
    backend = FakeCursorBackend()

    backend.click()
    backend.click()
    backend.click()

    assert backend.clicks == 3


def test_click_does_not_record_a_move() -> None:
    backend = FakeCursorBackend()

    backend.click()

    assert backend.calls == []


# --- SmoothingCursorBackend --------------------------------------------


def test_filtered_moves_reach_the_wrapped_backend_already_smoothed() -> None:
    wrapped = FakeCursorBackend()
    times = iter([0.0, 1.0 / 30.0, 2.0 / 30.0])
    smoothing = SmoothingCursorBackend(
        wrapped, filter=OneEuroFilter(clock=lambda: next(times))
    )

    smoothing.move_absolute(0.5, 0.5)
    smoothing.move_absolute(0.52, 0.48)
    smoothing.move_absolute(0.5, 0.5)

    # Three calls reached the wrapped backend, and -- because the input
    # jittered -- not simply echoed straight through unchanged.
    assert len(wrapped.calls) == 3
    assert wrapped.calls[0] == (0.5, 0.5)
    assert wrapped.calls != [(0.5, 0.5), (0.52, 0.48), (0.5, 0.5)]


def test_click_reaches_the_wrapped_backend_untouched() -> None:
    wrapped = FakeCursorBackend()
    smoothing = SmoothingCursorBackend(wrapped)

    smoothing.click()

    assert wrapped.clicks == 1


def test_click_does_not_itself_feed_the_filter() -> None:
    wrapped = FakeCursorBackend()
    smoothing = SmoothingCursorBackend(wrapped)

    smoothing.click()
    smoothing.click()
    smoothing.move_absolute(0.4, 0.6)

    # If click had fed the filter, this first move would already be
    # smoothed against clicks that carried no position of their own.
    assert wrapped.calls == [(0.4, 0.6)]


def test_click_after_a_filtered_move_lands_at_the_filtered_position() -> None:
    wrapped = FakeCursorBackend()
    times = iter([0.0, 1.0 / 30.0])
    smoothing = SmoothingCursorBackend(
        wrapped, filter=OneEuroFilter(min_cutoff=0.1, clock=lambda: next(times))
    )

    smoothing.move_absolute(0.5, 0.5)
    smoothing.move_absolute(0.9, 0.5)
    smoothing.click()

    filtered_position = wrapped.calls[-1]
    assert filtered_position != (0.9, 0.5)
    assert wrapped.clicks == 1


# --- press / release ---------------------------------------------------


def test_press_and_release_are_recorded_without_a_real_device() -> None:
    backend = FakeCursorBackend()

    backend.press()
    assert backend.held
    backend.release()

    assert (backend.presses, backend.releases, backend.clicks) == (1, 1, 0)
    assert not backend.held


def test_press_and_release_reach_the_wrapped_backend_untouched() -> None:
    wrapped = FakeCursorBackend()
    smoothing = SmoothingCursorBackend(wrapped)

    smoothing.press()
    smoothing.move_absolute(0.4, 0.6)
    smoothing.release()

    assert (wrapped.presses, wrapped.releases) == (1, 1)
    assert wrapped.calls == [(0.4, 0.6)]


# --- TriggerHold -------------------------------------------------------


def test_hold_presses_once_and_releases_on_the_last_holder() -> None:
    backend = FakeCursorBackend()
    hold = TriggerHold(backend)
    a, b = object(), object()

    assert hold.acquire(a)
    assert hold.acquire(b)
    assert backend.presses == 1

    assert hold.release(a)
    assert backend.held  # b still holds
    assert hold.release(b)
    assert (backend.presses, backend.releases) == (1, 1)


def test_hold_is_idempotent_per_owner() -> None:
    backend = FakeCursorBackend()
    hold = TriggerHold(backend)
    owner = object()

    assert hold.acquire(owner)
    assert not hold.acquire(owner)
    assert hold.release(owner)
    assert not hold.release(owner)

    assert (backend.presses, backend.releases) == (1, 1)


def test_releasing_a_hold_it_never_took_does_nothing() -> None:
    backend = FakeCursorBackend()
    hold = TriggerHold(backend)
    hold.acquire(object())

    assert not hold.release(object())
    assert backend.releases == 0


def test_click_while_held_does_not_lift_the_button() -> None:
    backend = FakeCursorBackend()
    hold = TriggerHold(backend)
    hold.acquire(object())

    hold.click()

    assert backend.clicks == 0
    assert backend.held


# --- Moves timed by the frame, not the clock ---------------------------


def _unused_clock() -> float:
    raise AssertionError("a stamped move must not read the filter's clock")


def test_a_stamped_move_is_filtered_at_the_given_time() -> None:
    """Two backends, same inputs: one timed by its clock, one by stamps
    carrying the same times. They must agree exactly."""
    times = [0.0, 0.05, 0.3]
    points = [(0.2, 0.2), (0.6, 0.4), (0.62, 0.41)]
    clocked = FakeCursorBackend()
    ticks = iter(times)
    by_clock = SmoothingCursorBackend(
        clocked, filter=OneEuroFilter(clock=lambda: next(ticks))
    )
    stamped_raw = FakeCursorBackend()
    by_stamp = SmoothingCursorBackend(
        stamped_raw, filter=OneEuroFilter(clock=_unused_clock)
    )

    for t, point in zip(times, points, strict=True):
        by_clock.move_absolute(*point)
        by_stamp.at(t).move_absolute(*point)

    assert stamped_raw.calls == clocked.calls


def test_stamped_leaves_an_unsmoothed_backend_alone() -> None:
    raw = FakeCursorBackend()

    assert stamped(raw, 1.0) is raw
    stamped(raw, 1.0).move_absolute(0.3, 0.7)
    assert raw.calls == [(0.3, 0.7)]


def test_stamped_without_a_time_is_the_backend_itself() -> None:
    smoothing = SmoothingCursorBackend(FakeCursorBackend())

    assert stamped(smoothing, None) is smoothing


def test_a_stamped_view_passes_buttons_through() -> None:
    raw = FakeCursorBackend()
    view = SmoothingCursorBackend(raw).at(1.0)

    view.press()
    view.release()
    view.click()

    assert (raw.presses, raw.releases, raw.clicks) == (1, 1, 1)
