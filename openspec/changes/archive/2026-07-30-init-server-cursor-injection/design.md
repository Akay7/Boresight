## Context

Boresight's server side doesn't exist yet. This change is the first slice
of it: prove that an HTTP request can move the OS cursor, on the Linux dev
box this project is built on. README.md ("Cursor injection") already
commits to a uinput virtual absolute pointer on Linux and `SendInput` on
Windows, selected by config flag — this change implements the Linux half
only, behind an interface that leaves room for the Windows backend later.

## Goals / Non-Goals

**Goals:**
- `uv`-managed Python project that another contributor can `uv sync` and run.
- A FastAPI endpoint that, given a target position, moves the real OS
  cursor via a Linux `uinput` virtual absolute pointer.
- A backend abstraction (`CursorBackend`) so the endpoint doesn't know or
  care whether it's talking to uinput, a future SendInput backend, or a
  test fake.
- `pytest` suite that exercises the endpoint and the backend contract
  without requiring a real `/dev/uinput` device (so it runs in CI).

**Non-Goals:**
- Windows `SendInput` backend (future change, same `CursorBackend` interface).
- Marker detection, homography, video streaming, or trigger handling —
  none of README's pipeline exists yet; this change only proves injection.
- Authentication/access control on the endpoint (flagged as a risk below,
  not solved here).
- Multi-monitor coordinate handling — single primary display only.

## Decisions

**Coordinate contract: normalized floats, not pixels.**
The endpoint accepts `x`, `y` as floats in `[0.0, 1.0]` (fraction of
screen width/height), not raw pixel coordinates. Rationale: this matches
where the value comes from in the full pipeline (homography output mapped
into screen space) and avoids baking a specific screen resolution into
the API contract. The backend converts normalized coordinates to uinput's
native `ABS_X`/`ABS_Y` range (0-32767), matching the HID descriptor note
already in README.md ("logical min 0, max 32767, 16-bit fields") so the
same range convention carries forward to the future SendInput/hardware
paths.
Alternative considered: raw pixel `x`/`y` with a `/screen` endpoint to
query resolution. Rejected for this change as unnecessary surface area —
normalized coordinates need no resolution lookup at all.

**Backend abstraction via a small Protocol, not a plugin system.**
`CursorBackend` is a one-method `Protocol` (`move_absolute(x: float, y:
float) -> None`). FastAPI's dependency-injection (`Depends`) supplies the
concrete backend, defaulting to the uinput implementation and overridden
with a fake in tests. Rationale: the real requirement is "swap the
backend under test," not a general plugin architecture — a Protocol plus
`Depends` is the smallest thing that provides that.

**uinput backend: `evdev.UInput`, device capabilities chosen as a
touchscreen, not a mouse or tablet.** `ABS_X`/`ABS_Y` ranged `(0, 32767)`
alone gets the device classified as a joystick and ignored by libinput.
Verified against a live X11 session that the remaining evdev-recognized
options for an absolute pointer behave very differently:
`BTN_LEFT` → udev tags `ID_INPUT_MOUSE`, and libinput runs the events
through relative-motion pointer acceleration instead of placing the
cursor directly (the opposite of what "absolute" is for); `BTN_TOOL_PEN`
→ tagged `ID_INPUT_TABLET`, and libinput's tablet backend rejected the
device outright for lacking real stylus capabilities. `BTN_TOUCH` +
`INPUT_PROP_DIRECT` → tagged `ID_INPUT_TOUCHSCREEN`, which libinput does
place directly at the reported coordinate — this is what
`UinputCursorBackend` uses, emitting `BTN_TOUCH` down, the `ABS_X`/`ABS_Y`
position, then `BTN_TOUCH` up per `move_absolute` call (a synthetic tap
at the target position). This mirrors the "Abs flag" distinction already
called out in README.md's Cursor injection section — the goal is a
cursor that jumps to the target instead of drifting from wherever it
was. Device is opened once at process startup (FastAPI lifespan), not
per request — device creation is the expensive/permission-sensitive
part.

**`uv` for the project, `pyproject.toml` at repo root.**
Matches README.md's existing "Software stack" entry for the prototype
language tooling; `uv sync` + `uv run pytest` / `uv run fastapi dev` are
the only two commands a contributor needs to know.

## Risks / Trade-offs

[`/dev/uinput` requires elevated permission] → Document a udev rule
(`KERNEL=="uinput", GROUP="input", MODE="0660"`) plus adding the running
user to the `input` group, so the server doesn't need to run as root.
Call this out explicitly in the change's README/setup notes.

[No auth on the movement endpoint — anything that can reach the port can
move the cursor] → Out of scope to solve here, but mitigate by defaulting
`uvicorn` to bind `127.0.0.1` rather than `0.0.0.0`, so it's loopback-only
until a real auth/transport story exists for the phone-streaming path.

[Normalized-coordinate contract could be the wrong call once real screen
geometry from `markers.toml` enters the picture] → Low cost to change
now (single endpoint, no external consumers yet); revisit when the
homography-output consumer (a later change) exists.

[`evdev.UInput` device creation can fail silently or block if the kernel
module isn't loaded] → Fail fast at FastAPI startup (lifespan) rather
than on first request, so a broken environment is obvious immediately
instead of surfacing as a mysterious 500 on first use.

[The touchscreen device type was chosen because it's the only capability
profile libinput places directly at the reported coordinate (see
Decisions above); real touchscreen support in libinput includes touch
arbitration/gesture heuristics not built for this use case, and on an
irregular multi-monitor test rig, large single-request jumps landed a
few percent off the exact target while small/edge cases were pixel-exact]
→ Acceptable for this change (single-request "does it move the cursor"
proof); a continuous stream of small per-frame updates — which is what
the real aim-tracking pipeline will actually send — is expected to avoid
the large-jump case entirely. Revisit if per-frame jitter shows up once
the full pipeline exists.

## Migration Plan

Greenfield — no existing deployment to migrate. Setup path for a new
contributor: `uv sync` → ensure `/dev/uinput` permissions (udev rule) →
`uv run fastapi dev src/boresight/server.py` → `POST /cursor/move` with
`{"x": 0.5, "y": 0.5}` → confirm the cursor jumps to screen center.

## Open Questions

- Should the movement endpoint be fire-and-forget (204) or echo back the
  resolved absolute coordinates it sent to uinput? Leaning 204 for now;
  revisit if a debug overlay client needs the echo.
- ~~Exact `python-uinput` vs raw `python-evdev` choice~~ — resolved
  during implementation: `evdev` (1.9.3, actively released) is used
  directly via `evdev.UInput`, not `python-uinput` (whose last release
  predates it substantially). `evdev.UInput` accepts the same
  `{ecodes.ABS_X: AbsInfo(...), ecodes.ABS_Y: AbsInfo(...)}` capability
  shape the uinput backend decision above describes.
