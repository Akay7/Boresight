## Why

`server.py` ends with `app = create_app()`: importing the module builds
a complete application with the default `ServerConfig` — no token, no
TLS — and opens nothing yet only because the backend is created at
startup. It exists so `uvicorn boresight.server:app` works, but that
path skips `main()` entirely: `config.validate()` never runs, so
`uvicorn boresight.server:app --host 0.0.0.0` serves an unauthenticated
mouse-moving endpoint to the whole network, which is exactly what the
network-access spec says must be impossible to configure by accident.
It also makes every `import boresight.server` (every test module) build
an app nobody uses.

## What Changes

- Remove the module-level `app = create_app()`. The server is started
  with `python -m boresight.server` (or the VS Code launch configs,
  which already run the module), which validates its configuration
  before building the app; tests and embedders call `create_app()`
  themselves, as they already do.
- Nothing in the repository refers to `boresight.server:app` (tests,
  README, `.vscode/launch.json`, firmware tools and the emulator test
  harness all use `create_app()` or `main()`), so no caller changes.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities
- `network-access`: importing the server module does not build a
  servable application, so the token check cannot be bypassed by
  serving a pre-built app by import path.

## Impact

- `src/boresight/server.py`: one line removed.
- Tests: `tests/test_network_access.py` gains a check that the module
  has no import-time app.
- Anyone who ran `uvicorn boresight.server:app` by hand must use
  `python -m boresight.server` instead. **BREAKING** for that
  (undocumented) invocation only.
