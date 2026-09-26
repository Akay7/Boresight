## Context

`create_app(backend_factory, marker_map_factory, config, display,
overlay_extra_margin_px)` builds the FastAPI app; `main()` parses
arguments, validates `ServerConfig` (refusing a routable bind without a
token), prints the phone URL and calls `uvicorn.run(create_app(...))`
with the app object itself. The trailing `app = create_app()` is a
second, unvalidated app built at import with `ServerConfig()`.

Callers checked: every test imports `create_app` (conftest,
`test_stream_e2e.py`, `test_sessions.py`, `test_network_access.py`,
`test_marker_routes.py`, `test_layout_source.py`,
`test_marker_source_routes.py`, `test_firmware_emulator.py`, which runs
`uvicorn.Server(uvicorn.Config(create_app(...)))`); `test_network_access.py`
stubs `uvicorn.run` and calls `main()`. `.vscode/launch.json` runs
`src/boresight/server.py` as a program. README documents
`python -m boresight.server` / `uv run python -m boresight.server`.
Nothing refers to `boresight.server:app`.

## Goals / Non-Goals

**Goals:**
- No application object at module level.

**Non-Goals:**
- Supporting `uvicorn --factory boresight.server:create_app`. It would
  work mechanically, but it also skips `main()`'s validation, so it is
  not documented or encouraged; `python -m boresight.server` is the one
  way to run the server.
- Changing `create_app`'s signature or defaults.

## Decisions

### Delete the line rather than replace it with a factory
A zero-argument factory for `uvicorn --factory` would reintroduce the
same bypass under a new name. Since no caller needs an import path, the
simplest correct change is to remove the object. The regression test
asserts `not hasattr(boresight.server, "app")`, so it cannot creep back.

## Risks / Trade-offs

- [Someone runs `uvicorn boresight.server:app` from memory] → uvicorn
  fails with "Attribute "app" not found in module", which is loud and
  points at the fix; the README already shows the supported command.
