"""The phone URL as a QR code, drawn in the terminal at startup.

The URL carries a 22-character random token, which is the point of it
and also what makes it miserable to type on a phone keyboard. The phone
has a camera; it can read the URL off the screen instead.

This is printed, never logged, for the same reason the URL line is: it
is the one intended disclosure of the token, to the operator at the
console. A log handler would persist it, and the redaction filter that
keeps `token=` values out of the logs cannot see a token inside a
picture. So it is also printed only to an interactive terminal -- a file
or a pipe is a log by another name.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Mapping
from typing import TextIO

import segno

# Two modules rather than the specified four: the code's own white
# background already separates it from the terminal around it, and it
# saves four columns and two lines.
QUIET_ZONE = 2
INDENT = "  "

# Black on bright white, set explicitly: drawing only the dark modules
# in the terminal's default colours inverts the code on a dark theme,
# and not every scanner reads an inverted code.
_COLOURS = "\x1b[30;107m"
_RESET = "\x1b[0m"

# Keyed by (top module dark, bottom module dark): one text line holds
# two module rows, which keeps the modules roughly square.
_HALF_BLOCKS = {
    (False, False): " ",
    (True, False): "▀",  # upper half block
    (False, True): "▄",  # lower half block
    (True, True): "█",  # full block
}


def render(data: str, *, quiet_zone: int = QUIET_ZONE) -> list[str]:
    """`data` as a QR code, one string per terminal line, colours included."""
    rows = [
        [bool(module) for module in row]
        for row in segno.make(data, micro=False).matrix_iter(border=quiet_zone)
    ]
    if len(rows) % 2:
        rows.append([False] * len(rows[0]))
    return [
        INDENT
        + _COLOURS
        + "".join(_HALF_BLOCKS[pair] for pair in zip(top, bottom, strict=True))
        + _RESET
        for top, bottom in zip(rows[::2], rows[1::2], strict=True)
    ]


def for_terminal(
    url: str,
    *,
    stream: TextIO | None = None,
    environ: Mapping[str, str] | None = None,
    terminal_size: os.terminal_size | None = None,
) -> str | None:
    """The code to print for `url` on `stream`, or None if it should not be.

    None, rather than something degraded, wherever the result could not
    be scanned: output that is not a terminal, a terminal too small to
    show the code whole, or one whose encoding has no block characters.
    The URL line is printed regardless, so nothing is lost.
    """
    stream = sys.stdout if stream is None else stream
    environ = os.environ if environ is None else environ
    if not stream.isatty() or environ.get("TERM") == "dumb":
        return None

    try:
        "".join(_HALF_BLOCKS.values()).encode(stream.encoding or "ascii")
        lines = render(url)
    except (UnicodeEncodeError, LookupError, segno.DataOverflowError):
        return None

    size = terminal_size or shutil.get_terminal_size()
    width = len(lines[0]) - len(_COLOURS) - len(_RESET)
    # The URL line and its blank lines sit above the code; a code that
    # scrolls half out of view is as useless as a wrapped one.
    if size.columns < width or size.lines < len(lines) + 4:
        return None
    return "\n".join(lines) + "\n"
