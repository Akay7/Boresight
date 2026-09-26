## Context

Four tunables shape aim feel today, each fixed at a different place:
`OneEuroFilter(min_cutoff, beta)` built per session by
`marker_source._aim_filter()` from two env vars; `HoldingPipeline`'s
`hold_s` from the `DEFAULT_HOLD_S` constant; and `UinputCursorBackend`'s
relative scale from `BORESIGHT_REL_SCALE` in its constructor. Each
session owns its filter and hold (cursor-ownership), and frames are
processed on executor threads, one frame per session at a time. The
server's remembered preferences are split between `ViewSettings.debug`
(server memory) and `MarkerSourceController` (source and margin). None
is persisted; `.boresight/` already holds the generated certificate.

## Goals / Non-Goals

**Goals:**
- One typed settings model with explicit ranges, used for the file, env,
  CLI and API alike, so a value is validated the same way wherever it
  comes from.
- Live changes that reach running sessions without locks on the frame
  path and without resetting a session's smoothing.
- A generic settings-file helper (path resolution, atomic write,
  unknown-table preservation) that other per-machine state can reuse.

**Non-Goals:**
- Exposing `d_cutoff`, capture resolution, JPEG quality or frame rate.
- Hot-reloading an edited file. The file is read at startup and written
  on save; the API is the live path.
- Per-session tuning. One set of values applies to every session.
- Calibration storage.

## Decisions

### Inventory of settings lost on restart
- Debug overlay default (`ViewSettings.debug`) — server memory only.
- Marker source (printed/on-screen) — always printed after a restart.
- Overlay margin — runtime changes lost; only the CLI flag survives.
- The four tuning values — env vars / a constant.
- The phone keeps nothing itself (no `localStorage`); its `CONFIG` block
  is build-time constants, not settings. So the phone needs no
  client-side persistence: everything it shows it reads from the server.

### Pydantic models, one per table
`Tuning` and `ViewPreferences` are frozen pydantic models with `Field`
ranges and `extra="forbid"`; `Settings` holds both and ignores unknown
top-level keys. Pydantic is already here via FastAPI, so the API's 422
on a bad value and the startup error on a bad file come from the same
constraints. The update request is a separate model with every field
optional but identically bounded — generated from `Tuning`'s fields so
the ranges cannot drift apart.

### Precedence is resolved once, at startup, into layers
`resolve_settings(path, env, cli)` reads the file (`tomllib`), overlays
env values, then CLI values, validates the result, and records which
keys came from env/CLI (`pinned`: key → "BORESIGHT_AIM_BETA" /
"--aim-beta"). Env parsing moves out of `inject.py` and
`marker_source.py`: those modules now take plain parameters.
Alternative: keep each module reading its own env var — rejected, the
precedence would be spread over four places and the file could not sit
between env and defaults.

Invalid env values used to fall back silently; now they stop startup.
A typo that silently does nothing is exactly what makes tuning by feel
confusing.

### Live store: an immutable snapshot swapped under a lock
`LiveSettings` holds the current `Tuning` as a frozen object. Updates
take a lock, validate `{**current, **changes}` and assign the new
snapshot — one reference assignment, so a reader sees either the old
or the new snapshot, never half of each. Sessions read the snapshot
once per frame (`SessionPipeline.process_frame`) and push the values
into their own filter and hold *on their own processing thread*, so the
filter's state is only ever touched by the thread already using it.
Alternatives: a lock inside `OneEuroFilter` (a lock on the hot path for
a value that changes a few times a session); a registry of sessions to
push to (bookkeeping on connect/disconnect, and a push from a request
thread would race the frame thread).

`OneEuroFilter.tune(min_cutoff, beta)` changes only the parameters; the
low-pass states and last sample stay, so the cursor does not jump.
`HoldingPipeline.hold_s` becomes a settable attribute; the window is
still measured from the last solve, so a shortened window takes effect
immediately.

### Relative scale is pushed to the backend
The backend is shared, not per session, and constructed by the
backend factory, so there is no per-frame read point. `rel_scale`
becomes a settable property on `UinputCursorBackend`, applied at
startup and after each update when the backend has it (`hasattr`), so
other platforms' backends need not know about it. A float assignment
read by the frame thread on its next move is safe in CPython.
`GET /settings` reports `rel_scale_supported` so the phone can disable
that slider.

### Save: merge into the raw file, write atomically
`LiveSettings` keeps the raw parsed file. Save builds the `tuning` and
`view` tables from what is in effect — except a pinned tuning key whose
value is unchanged since startup, which keeps the file's value (or
stays absent) — merges them over the raw file so unknown tables survive,
serializes, writes to a temp file in the same directory, `fsync`s and
`os.replace`s. A tiny serializer covers what the file holds (tables of
bool/int/float/str and lists of them); anything else raises rather than
writing something `tomllib` would read back differently. Comments in a
hand-edited file are not preserved; the file header says it is
machine-written. Alternative: add `tomli-w` — a dependency for a dozen
lines.

View preferences are read from their owners at save time
(`ViewSettings.debug`, the controller's source and margin) rather than
mirrored into the store, so there is one source of truth for each.

### Restoring the marker source without blocking startup
Selecting on-screen markers can wait up to 20 s for the overlay. The
lifespan hands `controller.select(SCREEN)` to the default executor and
does not await it; its failure is logged. The controller's lock
already serializes it against client selections and against shutdown.

### Routes live in their own router
`settings_routes.py` is an `APIRouter` like `markers.router`, included
in `create_app`; the token middleware covers it automatically. This
keeps `server.py`'s diff to wiring, which matters with several other
changes touching it concurrently.

## Risks / Trade-offs

- [A saved value silently loses to an env var on next start] → `GET
  /settings` names pins and the phone marks them.
- [Invalid env values now stop the server] → documented as BREAKING;
  the message names the variable.
- [Restoring on-screen markers at startup starts a process nobody asked
  for this run] → only if the operator saved it that way; a failure
  degrades to printed markers exactly like a failed tap.
- [Hand-edited comments are dropped on save] → header comment in the
  written file; the README says so.
- [`--config` in a directory the server cannot write] → save reports
  the `OSError` as a 500 with detail; the running values are unaffected.

## Migration Plan

Existing env vars keep working with the same meaning and now sit above
the file. No file exists until the first save, so behaviour is unchanged
for anyone who never uses the panel.
