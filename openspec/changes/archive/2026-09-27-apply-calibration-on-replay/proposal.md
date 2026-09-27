## Why

A recording saves the session's lens model and zero, but replay ignores
them, so a recording made with a calibrated camera or a zeroed gun
replays to a different aim than the player saw live. That defeats the
point of recording: a bug report should reproduce what happened.

## What Changes

- `pipeline.replay()` applies the lens model and zero stored in a
  recording's manifest (`recording.session.lens`, `recording.session.zero`)
  to every frame, so the replayed track matches the live one.
- A lens is applied only to frames of the size it was calibrated at, as
  live; a mismatched or unreadable one is reported and skipped rather
  than failing the replay.
- `replay(..., calibrated=False)` and `python -m boresight.pipeline
  --no-calibration` replay raw, for comparing a correction against none.
- Fixture sequences, which carry no `recording` block, replay exactly as
  before.

## Capabilities

### New Capabilities

### Modified Capabilities
- `aim-pipeline`: replay applies a sequence's own lens and zero when it
  carries them.
- `frame-recording`: the manifest's lens and zero are part of what makes
  a recording reproducible, not just context for a reader.

## Impact

- `src/boresight/pipeline.py` (`replay`, `main`), `src/boresight/recording.py`
  (a comment), tests in `tests/test_recording.py` and a new
  `tests/test_replay_calibration.py`, one README line.
