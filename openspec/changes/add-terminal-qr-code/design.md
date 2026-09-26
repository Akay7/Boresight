## Context

`server.main()` prints the phone URL (token included) with `print(...,
flush=True)` before `install_log_redaction()` and `uvicorn.run`. That
line is the one intended disclosure of the token (see the
`network-access` spec, "The token's value is kept out of server logs");
everything that goes through the `uvicorn.*` loggers is redacted by
`TokenRedactionFilter`.

## Goals / Non-Goals

**Goals:**
- A code a phone camera reads first time from an ordinary terminal.
- No output at all where it would be garbage: redirected stdout, a
  terminal too small, an encoding without block characters.

**Non-Goals:**
- Showing the code on the `/markers` page or the on-screen overlay. It
  would put the token on a page that is itself behind the token, or on
  a display anyone in the room sees; not worth it here.
- Honouring `NO_COLOR` or terminals without ANSI colour beyond
  `TERM=dumb` (the code is skipped there; see Decisions).

## Decisions

### `segno` for encoding, own renderer for output
`segno` is pure Python with no dependencies at all, maintained, and
exposes the module matrix directly (`matrix_iter`). `qrcode` is also
pure Python and would work; its built-in terminal printers either use
two columns per module or draw inverted, so it would be drawn by hand
anyway, and then `segno`'s zero-dependency footprint wins. `pyqrcode`
is unmaintained. Encoding QR by hand is not worth the error-correction
code.

Drawing the matrix is ~20 lines here, which keeps the output format
under our control and easy to test.

### Half blocks with explicit colours
Two module rows share one text line: `▀`, `▄`, `█` or a space, with the
foreground set to black and the background to bright white (SGR
`30;107`), reset at the end of each line. A typical tokenised LAN URL
fits version 3 at error correction L: 29 modules, so with the quiet
zone about 33 columns by 17 lines.

Setting colours explicitly makes the polarity right on both dark and
light terminal themes. The alternative, drawing light modules in the
default foreground, only works on dark themes and relies on the
scanner handling inverted codes.

The quiet zone is 2 modules rather than the specified 4: the white
background supplies the contrast against the terminal, and phone
scanners read it reliably; it saves 4 columns and 2 lines.

### When to print
Printed only if all hold, otherwise nothing (the URL line is still
there):
- `--no-qr` not given;
- `sys.stdout.isatty()` -- a file or pipe is a log, and a picture of the
  token in a log is exactly what this project avoids -- and `TERM` is not
  `dumb`;
- `shutil.get_terminal_size()` is at least the code's width in columns
  and its height in lines (plus the URL banner around it);
- `sys.stdout.encoding` can encode the block characters (a cp1252
  console cannot).

### Console, not logger
The code goes through `print(..., flush=True)` like the URL line, before
`install_log_redaction()`. Routing it through `logging` would be wrong
twice: the redaction filter cannot see a token inside a picture, and a
log handler may persist it. Printing it to a TTY only means it appears
where the URL is already shown and nowhere new.

## Risks / Trade-offs

- [Anyone who can see the screen, or a screen-share, can scan the token]
  → the same person could already read the URL; `--no-qr` for recordings.
- [Terminal scrollback or a `script` capture keeps the code] → the URL
  line is already there too; nothing new is persisted.
- [Legacy Windows console without VT processing shows raw escapes]
  → Windows Terminal and current conhost enable VT; `--no-qr` otherwise.
- [A very long hostname makes a bigger code] → the size check skips it
  rather than printing a wrapped, unscannable one.

## Migration Plan

None: additive; `uv sync` picks up the new dependency.
