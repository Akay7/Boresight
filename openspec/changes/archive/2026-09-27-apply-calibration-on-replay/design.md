## Context

Recordings (`recording.py`) already write the session's lens and zero
under `manifest.recording.session`, via `LensModel.as_dict()` and
`Zero.as_dict()`, but `pipeline.replay()` reads only `frames`. The
per-frame operation already takes `lens=` and `zero=` per call.

## Goals / Non-Goals

**Goals:** a recording replays to the aim seen live; a raw replay stays
one flag away; fixtures are untouched.

**Non-Goals:** re-running zeroing shots or lens capture from a recording;
replaying the dropout hold or smoothing (replay never did).

## Decisions

- **Apply by default.** A recording's purpose is reproduction, so the
  faithful replay is the default and `--no-calibration` the comparison.
  The alternative (opt-in) would make every bug report replay wrong
  unless the reader knows to ask.
- **Lens by frame size, as live.** The server looks a lens up by the
  decoded frame's size, so a stored lens for another size is not applied
  on replay either; this keeps a mid-recording resolution change honest.
- **Unreadable calibration is skipped, not fatal.** Replay is a
  debugging tool; a hand-edited manifest should still replay, with a
  printed note of what was left out.
- **One reader for both.** `replay_calibration()` reads the stored lens
  and zero; `replay()` and the CLI both use it, and the CLI prints whether a lens
  and a zero were used, so a printed track says what it is.

## Risks / Trade-offs

- Recordings made before this change replay differently if their session
  had a lens or zero → acceptable: they now match what was seen live,
  and `--no-calibration` gives the old output.
