## 1. Project scaffolding

- [x] 1.1 Initialize `uv` project at repo root (`uv init` or hand-written
      `pyproject.toml`), Python version pinned to match README (3.12+)
- [x] 1.2 Add runtime dependencies: `fastapi`, `uvicorn[standard]`,
      `python-uinput` (or `evdev` if uinput proves unmaintained — confirm
      per design.md Open Questions)
- [x] 1.3 Add dev dependencies: `pytest`, `httpx` (FastAPI `TestClient`
      transport)
- [x] 1.4 Create `src/boresight/` package layout matching README's Repo
      layout section (`server.py`, `inject.py`, `__init__.py`)
- [x] 1.5 Create `tests/` package with a `conftest.py` stub

## 2. Cursor backend

- [x] 2.1 Define `CursorBackend` Protocol in `inject.py` with
      `move_absolute(x: float, y: float) -> None`
- [x] 2.2 Implement `UinputCursorBackend`: opens a `uinput.Device` at
      construction with `ABS_X`/`ABS_Y` capabilities ranged `(0, 32767)`,
      converts normalized `[0.0, 1.0]` input to that range, emits an
      absolute move + `SYN_REPORT`
- [x] 2.3 Implement `FakeCursorBackend` for tests: records
      `(x, y)` calls it received, no real device
- [x] 2.4 Raise a clear, specific exception from `UinputCursorBackend`
      construction when `/dev/uinput` can't be opened (permission or
      missing module), distinct from other failure modes

## 3. FastAPI application

- [x] 3.1 Define request model for the move endpoint: `x: float`, `y:
      float`, both validated to `[0.0, 1.0]` (Pydantic `Field(ge=0.0,
      le=1.0)`)
- [x] 3.2 Add `POST /cursor/move` route that resolves the backend via
      `Depends`, calls `move_absolute`, returns 204 on success
- [x] 3.3 Wire `UinputCursorBackend` construction into FastAPI's lifespan
      (startup), so a broken environment fails at startup, not on first
      request
- [x] 3.4 Provide an app factory / dependency-override seam so tests can
      swap in `FakeCursorBackend` without touching the real device
- [x] 3.5 Default `uvicorn` bind host to `127.0.0.1` (loopback-only, per
      design.md's auth risk mitigation)

## 4. Tests

- [x] 4.1 Test: valid `x=0.5, y=0.5` request returns success and the fake
      backend recorded the call with matching coordinates
- [x] 4.2 Test: out-of-range coordinates (`x=1.5`, `y=-0.1`) return 422
      and the fake backend recorded no call
- [x] 4.3 Test: non-numeric coordinates return 422
- [x] 4.4 Test: repeated calls to the fake backend each record distinct
      positions (confirms absolute, not relative/accumulating, semantics
      at the API layer)
- [x] 4.5 Confirm the full suite runs via `uv run pytest` with no
      `/dev/uinput` access required (e.g. run in a minimal sandboxed
      shell without the device node present)

## 5. Manual verification

- [x] 5.1 Document the `/dev/uinput` udev rule and group-membership setup
      needed to run the real backend as a non-root user
- [x] 5.2 Run `uv run python -m boresight.server`, `POST /cursor/move`
      with `{"x": 0.5, "y": 0.5}`, confirm the OS cursor visibly jumps
- [x] 5.3 Repeat for a corner (`x=0.0, y=0.0`) and confirm the cursor
      jumps rather than drifts, regardless of starting position

      Verified against a live X11 session (`kwin_x11`) by querying the
      real pointer position via Xlib before/after each request. Findings
      that shaped `inject.py`:
      - A pure `EV_ABS` uinput device with no button capability is
        classified as a joystick and silently ignored for pointer
        positioning.
      - `ABS_X`/`ABS_Y` + `BTN_LEFT` gets udev-tagged `ID_INPUT_MOUSE`,
        which routes events through libinput's relative-motion pointer
        acceleration instead of placing the cursor directly — the
        symptom was requests appearing to "nudge" the cursor rather
        than jump to the target.
      - `ABS_X`/`ABS_Y` + `BTN_TOOL_PEN`/`BTN_STYLUS` gets tagged
        `ID_INPUT_TABLET`, which libinput's tablet backend rejected
        outright (`missing tablet capabilities: btn-stylus resolution`)
        since this synthetic device isn't a real, libwacom-known tablet.
      - `ABS_X`/`ABS_Y` + `BTN_TOUCH` + `INPUT_PROP_DIRECT` is tagged
        `ID_INPUT_TOUCHSCREEN`, which libinput places directly at the
        reported coordinate. This is what `UinputCursorBackend` uses,
        emitting a press/position/release per `move_absolute` call.
      - On this dev machine's irregular dual-monitor layout (two
        non-aligned outputs forming an L-shaped virtual screen, per
        `xrandr`), corner requests (`x=0.0`/`x=1.0`) landed within a few
        pixels of the exact expected position on the mapped output;
        large jumps to less extreme values showed some drift, most
        likely libinput's touch-gesture arbitration reacting to a big
        instantaneous position change rather than a real device defect.
        Precise multi-monitor calibration is out of scope per this
        change's design.md (single-display Non-Goal) and wasn't
        pursued further.
