## 1. Tooling and configuration

- [x] 1.1 Add `ruff` and `pre-commit` to `[dependency-groups] dev` in
      `pyproject.toml`, `uv sync`
- [x] 1.2 Add `[tool.ruff]` config: `select = ["E", "F", "I", "UP",
      "B"]`, line length matching project convention, target Python
      version 3.14
- [x] 1.3 Add `[tool.pytest.ini_options] filterwarnings` entries for
      `error::DeprecationWarning` and `error::PendingDeprecationWarning`

## 2. Fix the known deprecation warning

- [x] 2.1 Confirm the exact fix for the `starlette.testclient`
      `httpx`/`httpx2` warning (dependency swap vs. explicit
      `TestClient(transport=...)`) against current `starlette` docs
- [x] 2.2 Apply the fix in `tests/conftest.py` (and `pyproject.toml`
      dependencies if a package swap is needed)
- [x] 2.3 Run `uv run pytest -v` and confirm zero warnings in output

## 3. Baseline cleanup

- [x] 3.1 Run `uv run ruff check --fix .` across the repo, review the
      diff
- [x] 3.2 Run `uv run ruff format .` across the repo, review the diff
- [x] 3.3 Run `uv run ruff check .` again and confirm zero remaining
      violations (fix anything `--fix` couldn't handle automatically)
- [x] 3.4 Run `uv run pytest` and confirm the suite still passes after
      the baseline formatting/lint pass

      Only one real violation existed: `B008` on the `Depends(...)`
      default in `server.py`, which `--fix` can't auto-resolve since
      it's a semantic FastAPI pattern, not a style issue. Fixed by
      switching to `Annotated[CursorBackend, Depends(...)]`, the modern
      FastAPI DI style, which sidesteps the rule entirely instead of
      needing a `# noqa`. No formatting diffs were needed — the code
      was already `ruff format`-clean.

## 4. Pre-commit hook

- [x] 4.1 Add `.pre-commit-config.yaml` with `ruff check`, `ruff
      format --check`, and basic hygiene hooks (trailing whitespace,
      end-of-file fixer, check-toml, check-yaml)
- [x] 4.2 Run `uv run pre-commit run --all-files` and confirm it passes
      cleanly against the post-cleanup baseline
- [x] 4.3 Run `uv run pre-commit install` in this working copy so the
      hook is live

      First `--all-files` run had `end-of-file-fixer` auto-fix missing
      trailing newlines in `README.md` and `.gitignore` (pre-commit
      reports that as a "failure" because it modified files, not
      because anything is actually wrong — standard pre-commit
      behavior). Second run was clean across all 6 hooks.

## 5. Verify the gate actually blocks

- [x] 5.1 Introduce a deliberate lint violation in a scratch file,
      attempt `git commit`, confirm it's blocked with a clear message

      `scratch_lint_violation.py` with two unused imports, staged and
      committed: `ruff-check` failed with `F401`/`I001`, exit code 1,
      commit aborted (`git log` unchanged).
- [x] 5.2 Introduce a deliberate formatting violation (e.g. wrong
      quote style/spacing), attempt `git commit`, confirm it's blocked

      `scratch_format_violation.py` with unspaced dict literal, staged
      and committed: `ruff-check` passed but `ruff-format` failed
      (reformatted the file), exit code 1, commit aborted.
- [x] 5.3 Revert the scratch violations, confirm a normal commit
      proceeds cleanly through the hook

      Scratch files removed and unstaged (`git reset`), repo back to
      its pre-test state. Verified the "clean commit" side via `uv run
      pre-commit run --all-files` passing all 6 hooks (task 4.2) rather
      than via an actual `git commit` — deliberately did not create the
      first real commit of this project's code as a side effect of
      testing the hook; that's a separate decision for the user to make
      explicitly.

## 6. Documentation

- [x] 6.1 Document the one-time `uv run pre-commit install` setup step
      in README.md's dev-setup section, alongside the existing `uv
      sync`/`/dev/uinput` instructions
- [x] 6.2 Document the on-demand command (`uv run pre-commit run
      --all-files`) as what CI would eventually run
