## Why

Nothing checks the repository except a developer's own pre-commit hook,
which runs lint and format but not the tests, and nothing at all builds
the two C components. `requires-python = ">=3.14"` shuts out every
distribution Python older than a year, for the sake of one piece of
3.14-only syntax. And several documents have drifted: the README claims a
Windows input backend that does not exist, its accuracy table predates
sub-pixel corner refinement, the firmware README names a certificate
file the server never writes, and three copies of the OpenSpec skills
are tracked where only the `.claude/` one is used.

## What Changes

- GitHub Actions CI: lint, format and tests on Python 3.12 and 3.14; the
  Vulkan layer built with its unit tests, plainly and under ASan+UBSan;
  the ESP32-CAM firmware's host tests. The QEMU emulator tests stay
  opt-in and out of CI.
- The pre-commit hook also runs the test suite when Python files are
  staged.
- `requires-python = ">=3.12"`, ruff `target-version = "py312"`, the
  3.14-only unparenthesized `except A, B:` rewritten; `uv.lock`
  regenerated. `.python-version` stays 3.14 for local development.
- `[project.scripts]`: `boresight` and `boresight-overlay`, the same
  programs as `python -m boresight.server` / `python -m
  boresight.overlay`; README run commands use them.
- README, `pyproject.toml` and `overlay/backend.py` stop claiming a
  Windows input backend or Windows support.
- `.agent/` and `.opencode/` removed; `.claude/worktrees/` ignored.
- Firmware README copies `.boresight/server.crt`, the file that exists.
- README's "Marker visibility and accuracy" figures regenerated from the
  current detector.

## Capabilities

### New Capabilities
- `packaging`: which Python versions the package supports, and the
  commands an install provides.

### Modified Capabilities
- `code-quality-gate`: adds the test suite to the commit-time gate, and
  a CI requirement covering the Python, native and firmware checks.

## Impact

- New: `.github/workflows/ci.yml`, `tests/test_packaging.py`.
- `pyproject.toml`, `uv.lock`, `.pre-commit-config.yaml`, `.gitignore`.
- `src/boresight/{server,markers,marker_source,netaccess}.py`
  (exception syntax only), `src/boresight/overlay/backend.py`
  (docstring).
- `README.md`, `firmware/boresight-cam/README.md`.
- Removed: `.agent/`, `.opencode/`.
- Commit time grows by about 12 s when a Python file is staged.
