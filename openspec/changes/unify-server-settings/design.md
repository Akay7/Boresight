## Context

`settings.py` already resolves `[tuning]` and `[view]` with flag > env >
file > default, validates each layer with strict pydantic models, and
saves atomically while preserving tables it does not write. Every other
option is an argparse flag read directly in `server.main()`, and the
tracker's thresholds are module constants in `detect.py`.

## Goals / Non-Goals

**Goals:** every server option can live in one file; flags keep working
and override it; one validation path.

**Non-Goals:** changing the new tables from the phone (they need a
restart anyway: address, port, TLS); moving calibration results into
the file; environment variables for the new keys; watching the file.

## Decisions

- **Tables by concern, not one flat table.** `server`, `markers`,
  `detection`, `recording` beside `tuning` and `view`: a reader finds a
  setting by what it affects, and each table is one pydantic model.
- **Flags are overrides, resolved by the same code.** `main()` builds
  the dotted-key map of given flags (None = not given) and passes it to
  `resolve_settings`, as it already does for tuning. argparse defaults
  are therefore all None; the built-in defaults live only in the models.
  Booleans use `BooleanOptionalAction` so `--no-tls` can undo a file's
  `tls = true`; `--full-frame-detection` stays as the negative form of
  `--tracked-detection`, matching its existing name.
- **Only `tuning` and `view` are saved.** The phone changes only those;
  writing the rest would copy one-off flags into the file. The existing
  merge (`{**file, **written}`) already keeps other tables verbatim.
- **Tracker options as one value.** `detect.TrackerOptions` (frozen
  dataclass: `min_side_px`, `full_pass_every`, `backoff_frames`)
  replaces the `tracking: bool` plumbing; `None` means full search. A
  plain `bool` is still accepted where tests pass one.
- **The token may be in the file.** It is a per-machine secret stored
  in the same gitignored `.boresight/` directory as the TLS key. The
  README says so. It is never written by the server.
- **Calibration stays in its own files.** Lenses and zeroes are
  measurements keyed per camera and client and written by the server
  continually; mixing them into a hand-edited settings file would make
  every calibration rewrite it.

## Risks / Trade-offs

- A `[server]` typo now stops startup where a mistyped flag always did
  → consistent with the file's existing strictness.
- `GET /settings` does not expose the new tables → they are not
  changeable live; exposing read-only values can come later.
