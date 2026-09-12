from boresight.inject import FakeCursorBackend, SmoothingCursorBackend
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
