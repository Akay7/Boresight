## 1. Dependency

- [x] 1.1 Add `segno` with `uv add segno` (with a pyproject.toml comment saying why) and verify `uv.lock` is updated and `uv run python -c "import segno"` succeeds

## 2. Rendering

- [x] 2.1 Add `src/boresight/terminal_qr.py`: encode a URL and render it as half-block lines with explicit black-on-white colours and a 2-module quiet zone; verify with a unit test that turning the rendered lines back into modules reproduces segno's matrix
- [x] 2.2 Add the "should we print" check (TTY, `TERM` not `dumb`, terminal size, stdout encoding) returning the text or nothing; verify with unit tests for each skip reason and the happy path

## 3. Server integration

- [x] 3.1 Add `--no-qr` to `server.main()` and print the code with `print(..., flush=True)` right after the URL line, before log redaction is installed; verify with tests that the code is printed for a fake TTY, not printed with `--no-qr` or a non-TTY, and that no log record contains the token
- [x] 3.2 Note the QR and `--no-qr` briefly in README.md next to the phone URL instructions

## 4. Verification

- [x] 4.1 Run `uv run ruff check`, `uv run ruff format --check`, `uv run pytest -q` and `openspec validate --all --strict`; all pass
- [ ] 4.2 (Hardware) Scan the printed code with a real phone camera on a dark and a light terminal theme and confirm it opens the page with the token
