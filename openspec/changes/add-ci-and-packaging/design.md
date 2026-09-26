## Context

See proposal.md for the list. Facts that shaped the decisions:

- The only 3.14-only construct in the tree was PEP 758's unparenthesized
  `except A, B:`, in six places (`server.py` x3, `markers.py`,
  `marker_source.py`, `netaccess.py`). Every module under `src/` but the
  two `__init__.py` files already has `from __future__ import
  annotations`, so nothing relies on PEP 649's deferred evaluation;
  every `src` module imports on 3.12, and the full suite passes there
  unchanged. A grep for 3.13/3.14 standard-library additions
  (`copy.replace`, `warnings.deprecated`, `Queue.shutdown`,
  `PatternError`, `TypeIs`, `annotationlib`, ...) found none.
- `native/vulkan_overlay/CMakeLists.txt` already has
  `BORESIGHT_OVERLAY_BUILD_TESTS` and `BORESIGHT_OVERLAY_SANITIZE`, and
  falls back to fetching Vulkan-Headers when no system SDK is found.
- `firmware/boresight-cam/test_host` is plain CMake with no ESP-IDF, but
  its test reads `tests/fixtures/synthetic_video/frame_0001.jpg`, which
  is in Git LFS, as are all the Python fixtures.
- `openspec update` decides which tools to refresh from the directories
  present: in a copy with `.agent/` and `.opencode/` deleted it reported
  `Updating 1 tool(s): claude` and regenerated nothing else. The global
  config (`openspec config list`) holds workflows and a profile, not a
  tool list, so there is nothing to configure.

## Goals / Non-Goals

**Goals:**
- CI that runs what a developer can run locally, with the same commands.
- A supported-Python floor that distribution Pythons meet.

**Non-Goals:**
- Running the overlay's Qt tests in CI (they need the `overlay` extra
  and a display; they skip without it, as they do locally by default).
- A ThreadSanitizer job. The CMake comment documents one, but the ticket
  asked for ASan+UBSan; TSan can be added as another matrix row.
- Publishing wheels, or a Windows or macOS runner.
- Regenerating `.claude/` skills with `openspec update` (it would bump
  their generator version, an unrelated diff).

## Decisions

### One workflow, three jobs
`ci.yml` holds `python` (matrix 3.12 / 3.14), `vulkan-overlay` (matrix:
plain, ASan+UBSan) and `firmware-host`. One file keeps the triggers and
concurrency settings in one place; the jobs share nothing else, so they
run in parallel. `UV_PYTHON` is set per matrix row because
`.python-version` (3.14) would otherwise win for `uv sync` and `uv run`.
`uv sync --locked` fails if `uv.lock` is stale rather than quietly
re-resolving. Checkouts that need fixtures use `lfs: true`.
*Alternative:* a workflow per component with path filters. Skipped:
the whole run is a few minutes, and path filters are how a C change that
breaks a Python-side contract goes unnoticed.

### `libvulkan-dev` from apt
Installed so the build uses system headers instead of fetching them from
GitHub on every run. The CMake fallback still covers an image where the
package lacks headers. `-DCMAKE_BUILD_TYPE=Debug` so assertions are on.

### The whole suite in pre-commit, gated on Python files
A `local` hook, `uv run pytest -q`, `language: system`,
`pass_filenames: false`, `types: [python]`. The suite takes about 12 s
(12.6 s measured with `pre-commit run pytest --all-files`), which is
tolerable per commit and cheaper than a red CI run. Selecting only the
staged files' tests was rejected: the interesting breakages are
cross-module.

### 3.12 floor
The user approved 3.12. Ruff's `target-version = "py312"` makes ruff
itself reject 3.13+ syntax, which is what caught all six `except`
clauses; CI's 3.12 job catches standard-library use. `tests/
test_packaging.py` checks the console scripts resolve to the `main`s the
`python -m` forms run.

### Console scripts point at the existing `main`s
`boresight = "boresight.server:main"` and `boresight-overlay =
"boresight.overlay.__main__:main"`. Both already take `argv=None` and
return an exit code, so no wrapper is needed, and `main()`'s validation
(no token on a routable bind is refused) applies to both spellings. The
argparse `prog` still reads `python -m boresight.server`; that remains a
correct way to run it, so it was left alone. `python -m
boresight.pipeline` gets no script: it is a developer replay tool.

### Windows wording
There is no Windows cursor backend (`inject.py` has uinput only), so the
server does not run on Windows at all. The README's `SendInput`
paragraph, the Windows firewall recipe, the platform table's "Supported
in code" row, the file-tree comment and both roadmap mentions now say
"planned, not implemented" or are gone; the `cryptography` comment in
`pyproject.toml` no longer justifies itself by a Windows path. In
`src/`, `overlay/backend.py`'s docstring said one Qt widget "covers two
platforms"; it now says only X11 is exercised. Left as they are, because
they describe other software rather than claim support: `qt_backend.py`
saying what Qt maps a flag to on Windows, `vulkan_backend.py` probing
`vulkan-1.dll`, and `marker_source.py` explaining a thread-based pipe
reader as portable.

### Accuracy table
Regenerated two ways, both with the current detector (sub-pixel
refinement):
- The subset sweep reuses `tests/test_solve_partial_markers.py`'s
  fixture loading and `_solve_subset` over every subset of every
  `synthetic_video` frame: 5100 solves (the old 4844 came from an
  earlier render, as `improve-marker-detection/design.md` notes). Its
  numbers match that design's "after" column exactly: all markers 1.4 /
  1.5 mm, four corners 1.4 / 1.5, two opposite 2.3 / 6.1, two on one
  edge 7.9 / 24.2, one marker 13.5 / 131.7 mm, inside-hull max 3.0 mm,
  flagged max 131.7 mm. "Opposite sides" means the diagonal corner pairs
  and the opposite edge-midpoint pairs.
- The distance sweep re-rendered the scene with Blender 5.2 through
  `tests/generate_synthetic_video_fixture.render_sequence`, camera on
  the screen's axis aiming at its centre, with the fixtures' degradation
  and JPEG quality: 700 / 1000 / 1400 mm find 0 markers; 1800 mm finds 2
  (0.84 mm); 2200 / 2600 / 3000 mm find 8 (1.00 / 1.19 / 1.35 mm). The
  old "1.0-1.6 mm, 2200 and beyond" row is replaced by the three
  measured distances.
`tests/measure_detection.py` was also run; its per-fixture figures are
unchanged from `improve-marker-detection/design.md` and are not in the
README table.

## Risks / Trade-offs

- [CI not yet run on GitHub] → Every job's commands were run locally
  (see tasks.md) and the workflow passes `actionlint`; the runner image
  (package names, LFS quota) is the untested part.
- [Git LFS bandwidth on every CI run] → Two jobs fetch LFS; the fixtures
  are a few MB.
- [Commit hook now costs ~12 s] → Only when Python files are staged;
  `git commit --no-verify` remains for emergencies, and CI catches what
  that skips.
