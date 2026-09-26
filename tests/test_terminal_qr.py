"""The QR code of the phone URL printed at startup: that it decodes to
the URL, and that it is printed only where it can be scanned -- and never
into a log."""

from __future__ import annotations

import io
import logging
import os
import re

import cv2
import numpy as np
import pytest
import segno

from boresight import terminal_qr

TOKEN = "0123456789abcdefABCDEF"
URL = f"https://192.168.1.20:7331/?token={TOKEN}"
ROOMY = os.terminal_size((120, 60))
_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
_TOP = {" ": False, "▀": True, "▄": False, "█": True}
_BOTTOM = {" ": False, "▀": False, "▄": True, "█": True}


class FakeTerminal(io.StringIO):
    def __init__(self, *, tty: bool = True, encoding: str = "utf-8") -> None:
        super().__init__()
        self._tty = tty
        self._encoding = encoding

    def isatty(self) -> bool:
        return self._tty

    @property
    def encoding(self) -> str:  # StringIO's is read-only and None
        return self._encoding


def _modules(lines: list[str]) -> list[list[bool]]:
    """The module matrix drawn by `lines`, read back from the characters."""
    rows = []
    for line in lines:
        cells = _ESCAPE.sub("", line)[len(terminal_qr.INDENT) :]
        rows.append([_TOP[c] for c in cells])
        rows.append([_BOTTOM[c] for c in cells])
    return rows


def test_the_rendered_lines_reproduce_the_code() -> None:
    expected = [
        [bool(m) for m in row]
        for row in segno.make(URL, micro=False).matrix_iter(
            border=terminal_qr.QUIET_ZONE
        )
    ]
    drawn = _modules(terminal_qr.render(URL))

    # An odd module count is padded with one light row at the bottom.
    assert drawn[: len(expected)] == expected
    assert not any(any(row) for row in drawn[len(expected) :])


def test_the_rendered_code_decodes_to_the_url() -> None:
    """End to end through a real decoder, not just segno's own matrix."""
    modules = np.array(_modules(terminal_qr.render(URL)))
    image = np.where(modules, 0, 255).astype(np.uint8)
    image = cv2.copyMakeBorder(image, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    image = cv2.resize(image, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)

    decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(image)

    assert decoded == URL


def test_every_line_sets_and_resets_its_colours() -> None:
    """Explicit black on white, so the code has the right polarity on a
    dark and a light theme, and nothing bleeds into the next line."""
    for line in terminal_qr.render(URL):
        assert "\x1b[30;107m" in line
        assert line.endswith("\x1b[0m")


def test_an_interactive_terminal_gets_the_code() -> None:
    qr = terminal_qr.for_terminal(
        URL, stream=FakeTerminal(), environ={}, terminal_size=ROOMY
    )

    assert qr == "\n".join(terminal_qr.render(URL)) + "\n"


def test_redirected_output_gets_no_code() -> None:
    stream = FakeTerminal(tty=False)
    assert (
        terminal_qr.for_terminal(URL, stream=stream, environ={}, terminal_size=ROOMY)
        is None
    )


def test_a_dumb_terminal_gets_no_code() -> None:
    assert (
        terminal_qr.for_terminal(
            URL,
            stream=FakeTerminal(),
            environ={"TERM": "dumb"},
            terminal_size=ROOMY,
        )
        is None
    )


def test_an_encoding_without_block_characters_gets_no_code() -> None:
    assert (
        terminal_qr.for_terminal(
            URL,
            stream=FakeTerminal(encoding="cp1252"),
            environ={},
            terminal_size=ROOMY,
        )
        is None
    )


@pytest.mark.parametrize("size", [(30, 60), (120, 15)])
def test_a_terminal_too_small_gets_no_code(size: tuple[int, int]) -> None:
    assert (
        terminal_qr.for_terminal(
            URL,
            stream=FakeTerminal(),
            environ={},
            terminal_size=os.terminal_size(size),
        )
        is None
    )


# --- In the server's startup ------------------------------------------


@pytest.fixture
def started(monkeypatch):
    """Run `server.main` against a fake roomy terminal, serving nothing."""
    from boresight import server

    monkeypatch.setenv("COLUMNS", "120")
    monkeypatch.setenv("LINES", "60")
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "create_app", lambda **kwargs: object())

    def start(*extra: str) -> str:
        # Here rather than at fixture setup, which pytest's own output
        # capture would undo before the test body runs.
        terminal = FakeTerminal()
        monkeypatch.setattr("sys.stdout", terminal)
        server.main(["--host", "0.0.0.0", "--token", TOKEN, *extra])
        return terminal.getvalue()

    return start


def test_startup_prints_the_code_after_the_url(started) -> None:
    output = started()

    url_at = output.index(f"?token={TOKEN}")
    code_at = output.index("\x1b[30;107m")
    assert url_at < code_at


def test_no_qr_leaves_the_url_alone(started) -> None:
    output = started("--no-qr")

    assert f"?token={TOKEN}" in output
    assert "\x1b[30;107m" not in output


def test_the_code_and_token_never_reach_a_log(started, caplog) -> None:
    caplog.set_level(logging.DEBUG)

    output = started()

    assert "\x1b[30;107m" in output
    assert TOKEN not in caplog.text
    assert "▀" not in caplog.text and "▄" not in caplog.text
