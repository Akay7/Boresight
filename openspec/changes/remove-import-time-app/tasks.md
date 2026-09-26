## 1. Remove the import-time app

- [x] 1.1 Confirm nothing refers to `boresight.server:app` (tests, README, `.vscode/launch.json`, firmware tools, emulator harness) with a repository search, and record the result in design.md
- [x] 1.2 Delete `app = create_app()` from `server.py` and add a test in `tests/test_network_access.py` that the module has no `app` attribute; verify it fails before the deletion and passes after

## 2. Wrap-up

- [x] 2.1 Run `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check` and `openspec validate remove-import-time-app --strict`
