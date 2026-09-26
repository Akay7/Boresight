# code-quality-gate

## Purpose

Defines the automated code quality gate (linting, formatting, tests and
deprecation-warning enforcement) applied to the codebase at commit time,
on demand, and in continuous integration.

## Requirements

### Requirement: Commits are blocked on lint violations
A pre-commit hook SHALL run a linter (`ruff check`) against staged
Python files and SHALL block the commit if any violation is found.

#### Scenario: Commit with a lint violation is blocked
- **WHEN** a developer attempts to commit a Python file containing a
  lint violation from the configured rule set
- **THEN** the commit is aborted and the violation is reported

#### Scenario: Commit with no lint violations succeeds
- **WHEN** a developer attempts to commit Python files with no lint
  violations
- **THEN** the lint hook passes and does not block the commit

### Requirement: Commits are blocked on formatting drift
A pre-commit hook SHALL run a formatter check (`ruff format --check`)
against staged Python files and SHALL block the commit if any file is
not formatted according to the configured style.

#### Scenario: Unformatted file is blocked
- **WHEN** a developer attempts to commit a Python file that does not
  match the configured formatter output
- **THEN** the commit is aborted and the affected file is reported

### Requirement: The quality gate is runnable on demand, not only at commit time
The full set of checks configured for the pre-commit hook SHALL be
runnable as a single on-demand command against the whole repository,
independent of the git commit flow (e.g. for CI or manual review).

#### Scenario: Running the gate against the whole repo
- **WHEN** a developer or CI system runs the on-demand quality-check
  command
- **THEN** every configured check runs against all tracked files and
  reports pass/fail without requiring a git commit to be in progress

### Requirement: Dependency deprecation warnings fail the test suite
The test suite SHALL treat `DeprecationWarning` and
`PendingDeprecationWarning` raised during test execution as errors,
rather than allowing tests to pass while printing an ignored warning.

#### Scenario: A deprecation warning fails the affected test
- **WHEN** a test run triggers a `DeprecationWarning` or
  `PendingDeprecationWarning` from application or dependency code
- **THEN** the test that triggered it fails, rather than passing with
  the warning only printed to output

#### Scenario: A warning-free test run passes cleanly
- **WHEN** the test suite runs against code with no unfiltered
  deprecation warnings
- **THEN** the full suite passes with no `DeprecationWarning` or
  `PendingDeprecationWarning` output

### Requirement: Commits are blocked on failing tests
A pre-commit hook SHALL run the whole test suite whenever a commit
stages at least one Python file, and SHALL block the commit if any test
fails. A commit that stages no Python file SHALL NOT run the suite.

#### Scenario: A commit that breaks a test is blocked
- **WHEN** a developer attempts to commit a Python change that makes a
  test fail
- **THEN** the commit is aborted and the failing test is reported

#### Scenario: A documentation-only commit does not run the suite
- **WHEN** a developer commits changes to Markdown files only
- **THEN** the test hook is skipped

### Requirement: Every push and pull request is checked in CI
Continuous integration SHALL run, on every pull request and every push
to the main branch: the linter, the formatter check and the test suite
on the oldest supported Python and on the Python the project is
developed on; a build of the Vulkan present layer with its unit tests,
once plainly and once under AddressSanitizer and
UndefinedBehaviorSanitizer; and the ESP32-CAM firmware's host tests. It
SHALL NOT run the firmware emulator tests, which stay opt-in.

#### Scenario: A change that only fails on the oldest Python is caught
- **WHEN** a pull request uses syntax or a standard-library API the
  oldest supported Python lacks
- **THEN** that Python's CI job fails

#### Scenario: A memory error in the layer's tested code is caught
- **WHEN** a change introduces an out-of-bounds read in code the layer's
  unit tests exercise
- **THEN** the sanitizer job fails

#### Scenario: The emulator tests are not run
- **WHEN** CI runs
- **THEN** the firmware emulator tests are skipped, and no job needs
  Docker or ESP-IDF
