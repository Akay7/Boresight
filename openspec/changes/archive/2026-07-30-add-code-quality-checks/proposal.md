## Why

The server-side code (`src/boresight/`, `tests/`) has no automated quality
gate: nothing catches lint errors, formatting drift, or deprecated-API
usage before it lands. This is already visible in practice — the test
suite currently emits a `StarletteDeprecationWarning` ("Using `httpx`
with `starlette.testclient` is deprecated; install `httpx2` instead")
that nobody is required to look at or fix. As the codebase grows past
the single-endpoint slice it is today, catching this class of issue at
commit time is far cheaper than catching it later.

## What Changes

- Add `ruff` for linting and formatting (single tool, fast, already the
  de facto standard for `uv`-managed projects — replaces the
  black/flake8/isort combination this project never had in the first
  place).
- Add `pre-commit` (the `pre-commit` framework) wired to run `ruff
  check` and `ruff format --check` on every commit, plus basic hygiene
  hooks (trailing whitespace, end-of-file fixer, TOML/YAML syntax
  checks).
- Add a deprecation-warnings check to the test suite (`pytest` configured
  to fail on unfiltered `DeprecationWarning`/`PendingDeprecationWarning`
  by default), so a deprecated dependency API doesn't silently sit in a
  warning nobody reads.
- Fix the currently-known instance that check would catch: replace the
  deprecated `httpx` transport `starlette.testclient.TestClient` uses
  with `httpx2`, clearing the existing warning.
- Document the local dev workflow (`uv run pre-commit install`, `uv run
  pre-commit run --all-files`) in the README.
- No behavior change to the `/cursor/move` endpoint or the cursor
  injection backend — this change is tooling/process only.

## Capabilities

### New Capabilities
- `code-quality-gate`: pre-commit-enforced linting, formatting, and
  deprecation-warning checks that block a commit (and are runnable
  on-demand) when violated.

### Modified Capabilities
(none — no existing spec's runtime requirements change)

## Impact

- New dev dependencies: `ruff`, `pre-commit`.
- Dependency change: `httpx` → `httpx2` (or both, per whatever
  `starlette.testclient` actually requires — confirmed during
  implementation) as the test transport dependency.
- New files: `.pre-commit-config.yaml`, `ruff` config (in
  `pyproject.toml`).
- `pyproject.toml`: `[tool.ruff]`, `[tool.pytest.ini_options]`
  `filterwarnings` additions.
- Every contributor now needs `uv run pre-commit install` once per
  clone for the gate to run locally; CI (if/when it exists) would run
  `uv run pre-commit run --all-files` as a required check — this change
  does not add CI itself, only the local gate and the command CI would
  eventually call.
