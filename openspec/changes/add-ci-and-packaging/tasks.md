## 1. Python floor

- [x] 1.1 Set `requires-python = ">=3.12"` and ruff `target-version = "py312"`; verify `uv run ruff check` reports the 3.14-only syntax
- [x] 1.2 Parenthesize the six `except A, B:` clauses; verify `uv run ruff check` passes
- [x] 1.3 Check for PEP 649 reliance and 3.13+ stdlib APIs; verify every `src` module imports on Python 3.12
- [x] 1.4 Regenerate `uv.lock`; verify `uv sync --locked` succeeds on 3.12 and 3.14
- [x] 1.5 Run the suite on both; verify `uv run --python 3.12 pytest -q` and `uv run --python 3.14 pytest -q` pass

## 2. Packaging

- [x] 2.1 Add `[project.scripts]` `boresight` and `boresight-overlay`; verify `uv run boresight --help` and `uv run boresight-overlay --help` print usage and `boresight --host 0.0.0.0` without a token exits 2
- [x] 2.2 Add `tests/test_packaging.py`; verify it passes
- [x] 2.3 Update README run commands to the scripts, mentioning `python -m` as an alternative; verify no `uv run python -m boresight.server` remains

## 3. CI and hooks

- [x] 3.1 Write `.github/workflows/ci.yml` (python matrix 3.12/3.14; Vulkan layer plain and ASan+UBSan with ctest; firmware host tests); verify with `actionlint`
- [x] 3.2 Run each job's commands locally; verify all pass
- [x] 3.3 Add the `pytest` local hook to `.pre-commit-config.yaml`; verify `uv run pre-commit run pytest --all-files` passes and note its runtime

## 4. Documentation and repo hygiene

- [x] 4.1 Remove the Windows input claims from `pyproject.toml`, README and `overlay/backend.py`; verify `grep -n "SendInput\|Windows" README.md` shows only "planned, not implemented" wording
- [x] 4.2 Remove `.agent/` and `.opencode/`; verify `openspec update` in a copy refreshes only Claude Code
- [x] 4.3 Ignore `.claude/worktrees/`; verify `git status` no longer lists it
- [x] 4.4 Fix the certificate path in `firmware/boresight-cam/README.md`; verify it matches `netaccess.CERT_NAME`
- [x] 4.5 Regenerate README's "Marker visibility and accuracy" figures; verify they match the sweep output recorded in design.md

## 5. Gate

- [x] 5.1 `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check` and `openspec validate add-ci-and-packaging --strict` pass
