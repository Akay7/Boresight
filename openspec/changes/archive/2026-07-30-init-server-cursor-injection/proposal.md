## Why

Boresight's server side (README.md "Repo layout", "Software stack") doesn't
exist yet — there's no project scaffolding, no way to run a server, and no
proof that the PC can actually move the OS cursor programmatically. Before
building marker detection, homography, or video streaming, we need the
smallest possible slice that proves the injection primitive works end to
end: an HTTP request in, the OS cursor moving on screen out. Everything
else in the pipeline (detect.py, solve.py, filter.py) is worthless without
this working.

## What Changes

- Initialize the Python project with `uv` (pyproject.toml, lockfile, dev
  dependencies).
- Add a FastAPI application exposing an endpoint that moves the OS mouse
  cursor to an absolute screen position.
- Implement a Linux cursor-injection backend using `uinput` (the dev/target
  platform per README's "Cursor injection" section — a uinput virtual
  absolute pointer). Windows `SendInput` is out of scope for this change.
- Add `pytest` with unit tests covering the FastAPI endpoint (request
  validation, backend invocation) using a fake/mocked injection backend, so
  the suite doesn't require real `uinput` device permissions to run in CI.
- No video, detection, homography, filtering, or trigger handling yet —
  this change is scoped strictly to proving the injection path.

## Capabilities

### New Capabilities
- `cursor-injection`: HTTP-triggered absolute cursor movement on the host
  OS, via a pluggable platform backend (Linux `uinput` for this change).

### Modified Capabilities
(none — first change in this project)

## Impact

- New code: `pyproject.toml`, `src/boresight/server.py` (FastAPI app),
  `src/boresight/inject.py` (uinput backend), `tests/`.
- New runtime dependency: `python-uinput` (or equivalent) on Linux, which
  requires `/dev/uinput` write access — document the permission/udev rule
  needed to run outside a container as root.
- New dev dependency: `pytest`, `httpx` (FastAPI's recommended test client
  transport), `uv` as the project/dependency manager replacing any
  ad-hoc pip usage.
- No changes to existing code (project has no prior server-side code).
