from boresight.inject import FakeCursorBackend


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
