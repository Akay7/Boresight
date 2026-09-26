## ADDED Requirements

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
