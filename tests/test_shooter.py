"""`CursorArbiter`: one session's aim drives the cursor at a time."""

from __future__ import annotations

import logging

from boresight.inject import FakeCursorBackend
from boresight.shooter import OWNER_IDLE_S, CursorArbiter


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _Session:
    """Stands in for a session's stats: compared by identity only."""

    def __init__(self, name: str) -> None:
        self.name = name

    def label(self) -> str:
        return self.name


def _arbiter() -> tuple[CursorArbiter, FakeCursorBackend, _Clock]:
    backend = FakeCursorBackend()
    clock = _Clock()
    return CursorArbiter(backend, clock=clock), backend, clock


def test_a_free_cursor_goes_to_the_first_session_to_aim() -> None:
    arbiter, backend, _ = _arbiter()
    a, b = _Session("a"), _Session("b")

    arbiter.cursor_for(a, a.label).move_absolute(0.1, 0.1)
    arbiter.cursor_for(b, b.label).move_absolute(0.9, 0.9)

    assert backend.calls == [(0.1, 0.1)]
    assert arbiter.status(a) == "yours"
    assert arbiter.status(b) == "other"


def test_nobody_owns_a_fresh_cursor() -> None:
    arbiter, _, _ = _arbiter()

    assert arbiter.status(_Session("a")) == "free"


def test_pressing_takes_the_cursor_from_its_owner() -> None:
    arbiter, backend, _ = _arbiter()
    a, b = _Session("a"), _Session("b")
    arbiter.cursor_for(a, a.label).move_absolute(0.1, 0.1)

    arbiter.claim(b, b.label)
    arbiter.cursor_for(a, a.label).move_absolute(0.2, 0.2)
    arbiter.cursor_for(b, b.label).move_absolute(0.8, 0.8)

    assert backend.calls == [(0.1, 0.1), (0.8, 0.8)]
    assert arbiter.status(b) == "yours"


def test_an_owner_that_stops_aiming_lapses() -> None:
    arbiter, backend, clock = _arbiter()
    a, b = _Session("a"), _Session("b")
    arbiter.cursor_for(a, a.label).move_absolute(0.1, 0.1)

    clock.now += OWNER_IDLE_S * 0.9
    arbiter.cursor_for(b, b.label).move_absolute(0.9, 0.9)
    assert arbiter.status(a) == "yours"

    clock.now += OWNER_IDLE_S * 0.2
    assert arbiter.status(a) == "free"
    arbiter.cursor_for(b, b.label).move_absolute(0.8, 0.8)

    assert backend.calls == [(0.1, 0.1), (0.8, 0.8)]
    assert arbiter.status(b) == "yours"


def test_an_owner_that_keeps_aiming_keeps_the_cursor() -> None:
    arbiter, backend, clock = _arbiter()
    a, b = _Session("a"), _Session("b")
    for _ in range(10):
        arbiter.cursor_for(a, a.label).move_absolute(0.1, 0.1)
        arbiter.cursor_for(b, b.label).move_absolute(0.9, 0.9)
        clock.now += OWNER_IDLE_S * 0.5

    assert (0.9, 0.9) not in backend.calls


def test_releasing_frees_the_cursor_at_once() -> None:
    arbiter, backend, _ = _arbiter()
    a, b = _Session("a"), _Session("b")
    arbiter.cursor_for(a, a.label).move_absolute(0.1, 0.1)

    arbiter.release(a)
    arbiter.cursor_for(b, b.label).move_absolute(0.9, 0.9)

    assert backend.calls == [(0.1, 0.1), (0.9, 0.9)]


def test_releasing_a_cursor_it_does_not_own_does_nothing() -> None:
    arbiter, _, _ = _arbiter()
    a, b = _Session("a"), _Session("b")
    arbiter.claim(a, a.label)

    arbiter.release(b)

    assert arbiter.status(a) == "yours"


def test_a_claim_is_not_lapsed_before_the_first_frame() -> None:
    arbiter, _, clock = _arbiter()
    a = _Session("a")
    clock.now = 100.0

    arbiter.claim(a, a.label)

    assert arbiter.status(a) == "yours"


def test_buttons_pass_straight_through_the_gate() -> None:
    arbiter, backend, _ = _arbiter()
    a, b = _Session("a"), _Session("b")
    arbiter.claim(a, a.label)
    gate = arbiter.cursor_for(b, b.label)

    gate.press()
    gate.release()
    gate.click()

    assert (backend.presses, backend.releases, backend.clicks) == (1, 1, 1)


def test_a_handover_is_logged_by_label(caplog) -> None:
    arbiter, _, _ = _arbiter()
    a, b = _Session("phone 10.0.0.2:5000"), _Session("esp32-cam 10.0.0.3:6000")

    with caplog.at_level(logging.INFO, logger="boresight"):
        arbiter.cursor_for(a, a.label).move_absolute(0.1, 0.1)
        arbiter.cursor_for(a, a.label).move_absolute(0.1, 0.1)
        arbiter.claim(b, b.label)

    lines = [r.getMessage() for r in caplog.records if "cursor now" in r.getMessage()]
    assert lines == [
        "cursor now follows phone 10.0.0.2:5000",
        "cursor now follows esp32-cam 10.0.0.3:6000",
    ]


def test_a_closed_gate_frees_the_cursor_and_drops_later_moves() -> None:
    """A frame still on an executor thread when its session ends must not
    take the cursor back for a session that is gone."""
    arbiter, backend, _ = _arbiter()
    a, b = _Session("a"), _Session("b")
    gate = arbiter.cursor_for(a, a.label)
    gate.move_absolute(0.1, 0.1)

    gate.close()
    gate.move_absolute(0.5, 0.5)

    assert arbiter.status(a) == "free"
    arbiter.cursor_for(b, b.label).move_absolute(0.9, 0.9)
    assert backend.calls == [(0.1, 0.1), (0.9, 0.9)]


def test_closing_a_gate_leaves_another_owner_alone() -> None:
    arbiter, _, _ = _arbiter()
    a, b = _Session("a"), _Session("b")
    arbiter.claim(a, a.label)

    arbiter.cursor_for(b, b.label).close()

    assert arbiter.status(a) == "yours"
