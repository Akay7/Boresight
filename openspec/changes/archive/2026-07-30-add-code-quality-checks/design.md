## Context

The codebase currently is exactly what `init-server-cursor-injection`
produced: `src/boresight/{inject,server}.py`, a small `tests/` suite, and
a `uv`-managed `pyproject.toml`. There is no linter, no formatter, and no
hook of any kind — nothing stops a lint issue, a formatting drift, or a
deprecated-API call from landing. The concrete evidence of the gap:
`uv run pytest` already prints a `StarletteDeprecationWarning` about the
`httpx` transport `starlette.testclient.TestClient` uses, and nothing
in the current setup would ever force that to be looked at.

## Goals / Non-Goals

**Goals:**
- One fast, `uv`-native tool for linting and formatting (`ruff`).
- A `pre-commit` config that runs that tool (plus cheap hygiene hooks)
  on every commit, and can also run on-demand / in CI via the same
  command.
- Deprecation warnings from dependencies fail the test suite instead of
  printing quietly, so they get fixed instead of ignored.
- Fix the one deprecation warning that already exists today, as proof
  the check works and to leave the repo clean when the hook turns on.

**Non-Goals:**
- Static type checking (`mypy`/`pyright`). Worth a future change; adding
  it alongside lint/format here would conflate two different kinds of
  "quality gate" (style/correctness-adjacent vs. type soundness) and
  risks a much noisier first pass across untyped code.
- Setting up CI (GitHub Actions or similar). This change produces the
  command CI would run (`uv run pre-commit run --all-files`); wiring an
  actual CI pipeline is separate.
- Rewriting existing code beyond what's needed to pass the new checks
  (the `httpx2` swap and whatever `ruff --fix`/`ruff format` change on
  the existing two source files and test files).

## Decisions

**`ruff` for both lint and format, not black + flake8 + isort.**
The project has no formatter/linter yet, so there's no migration cost to
weigh — `ruff` replaces what would otherwise be three separate tools
with one, is already the default choice for new `uv` projects, and is
fast enough that running it in a commit hook has no perceptible cost.

**Rule set: ruff defaults plus bugbear, pyupgrade, and import sorting —
not an exhaustive strict set.** Concretely: `select = ["E", "F", "I",
"UP", "B"]` (pycodestyle errors, pyflakes, isort, pyupgrade, bugbear).
`UP` matters directly for the "some modules are deprecated" complaint —
it flags old-style syntax/API usage that has a modern replacement,
which is exactly the class of problem being targeted. Starting from
ruff's full "ALL" rule set was considered and rejected: on a first pass
over a real (if small) codebase it produces a lot of stylistic noise
unrelated to the actual complaint, which would make the first commit
under the new gate needlessly large and would make it harder to tell
signal from noise going forward.

**`pytest` fails on unfiltered `DeprecationWarning` /
`PendingDeprecationWarning`.** Via `[tool.pytest.ini_options]
filterwarnings = ["error::DeprecationWarning",
"error::PendingDeprecationWarning"]`. This is what actually catches
"some modules are deprecated" as a hard failure instead of a warning
nobody reads — `ruff`/formatting alone wouldn't have caught the
`httpx`/`starlette.testclient` issue that motivated this change, since
that's a runtime warning from a dependency's behavior, not a lint rule
about this repo's source.

**Fix the `httpx` → `httpx2` warning as part of this change, not a
follow-up.** Leaving a known-failing check red the moment the gate is
turned on defeats the purpose. Exact mechanism (swap the dependency,
or pass an explicit transport to `TestClient`) gets confirmed against
`starlette`'s current docs during implementation — whichever fix
actually clears the warning without breaking `tests/conftest.py`'s
fixtures.

**Repo-wide `ruff --fix` / `ruff format` pass happens once, before the
hook is wired up.** Otherwise the first person to commit after this
change lands hits a wall of pre-existing violations unrelated to
whatever they were actually trying to commit.

## Risks / Trade-offs

[A stricter rule set surfaces more real issues but costs more one-time
cleanup and reviewer attention] → Start with the modest `E/F/I/UP/B`
set described above; expanding the rule set is a cheap, separate future
change once the baseline is clean and normal to work with.

[`pre-commit` requires each contributor to run `uv run pre-commit
install` once — if they don't, the hook silently doesn't run locally
and violations only surface whenever someone eventually runs `pre-commit
run --all-files` or wires CI] → Document the one-time setup step
prominently in the README's dev-setup section (next to the existing
`uv sync` / `/dev/uinput` instructions from the previous change).

[Turning `DeprecationWarning` into a test failure could break on a
future dependency upgrade that introduces new deprecation warnings
unrelated to any code change here] → Acceptable and intended — that's
exactly the "some modules are deprecated" problem the proposal names;
a warning appearing after a routine `uv lock --upgrade` should be
loud, not silent.

## Migration Plan

1. Add `ruff` + `pre-commit` as dev dependencies, add `[tool.ruff]` and
   the `filterwarnings` config to `pyproject.toml`.
2. Run `uv run ruff check --fix .` and `uv run ruff format .` once
   across the existing codebase to establish a clean baseline.
3. Fix the `httpx`/`httpx2` deprecation warning; confirm `uv run pytest`
   is warning-free.
4. Add `.pre-commit-config.yaml`, run `uv run pre-commit run
   --all-files` to confirm it's clean against the now-fixed baseline.
5. `uv run pre-commit install` so the hook is live in this working copy;
   document the same step for other contributors.

No rollback complexity — this is additive tooling with no runtime
behavior change; reverting the commit removes the gate.

## Open Questions

- Should `mypy`/`pyright` be a near-term follow-up change, or left
  until the codebase is bigger? Leaning toward "follow-up, not now" —
  noted as a Non-Goal above.
- ~~Does clearing the `httpx`/`httpx2` warning require adding `httpx2`
  as a dependency~~ — resolved during implementation: yes. Reading
  `starlette.testclient`'s source directly (rather than docs) showed it
  tries `import httpx2` first and only falls back to `httpx` — with a
  warning — if `httpx2` isn't installed. Swapping the dev dependency
  from `httpx` to `httpx2` avoids the fallback branch entirely, so the
  warning is never emitted (not just filtered). Also confirmed
  `StarletteDeprecationWarning` subclasses `UserWarning`, not
  `DeprecationWarning` — the `filterwarnings` config added in task 1.3
  would not have caught this warning anyway, which is further reason
  the dependency swap (not a filter) is the correct fix.
