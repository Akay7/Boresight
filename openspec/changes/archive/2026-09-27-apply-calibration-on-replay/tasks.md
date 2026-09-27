## 1. Replay

- [x] 1.1 Read `recording.session.lens` / `.zero` from the manifest in `pipeline.replay()`, skipping (with a reason) any that do not parse
- [x] 1.2 Pass the zero to every frame and the lens only to frames of its image size; add `calibrated=True`
- [x] 1.3 `python -m boresight.pipeline --no-calibration`, and print which calibration was applied
- [x] 1.4 Update the recording manifest comment that said replay does not apply them

## 2. Tests and docs

- [x] 2.1 Tests: zero applied, lens applied, lens size mismatch skipped, `calibrated=False` equals raw, fixture replay unchanged, unreadable calibration skipped
- [x] 2.2 Record round trip with a zeroed session replays to the live aim
- [x] 2.3 README: one line in "Saving what just happened"
