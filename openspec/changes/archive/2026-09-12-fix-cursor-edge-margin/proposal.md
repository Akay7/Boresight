## Why

`inject.py`'s cursor device is classified `ID_INPUT_TOUCHSCREEN` by
udev/libinput — required (per `cursor-injection`'s design) so
`move_absolute` places the cursor directly instead of through
relative-motion acceleration. But `aim-pipeline` clamps an off-panel
aim point to exactly `0.0`/`1.0`, and a legitimately-solved aim point
can land there too when the player aims near the bezel, which is
common since that's where the markers themselves sit. A pointer
reaching the literal screen edge is exactly what several desktop
environments (observed: KDE's Electric Borders, touch edge-swipe
gestures such as Overview/Show Desktop) watch for to trigger a bound
action — in practice, windows minimizing or rearranging themselves with
no apparent cause, reported during normal use of the trigger feature
added in `add-trigger-click`.

## What Changes

- `aim-pipeline`'s clamp keeps the emitted normalized position a small
  margin away from the literal `0.0`/`1.0` edge (both for the
  defensive off-panel clamp and for a legitimately-solved near-edge
  aim point), so the cursor device never reports the exact screen-edge
  coordinate that triggers desktop-environment edge/corner gestures.

## Capabilities

### Modified Capabilities
- `aim-pipeline`: the off-panel clamp requirement now bounds into
  `[margin, 1.0 - margin]` rather than `[0.0, 1.0]`.

## Impact

- Changed code: `src/boresight/pipeline.py` (`_clamp_unit`, new
  `EDGE_MARGIN` constant), `tests/test_pipeline.py` (updated expected
  values for the off-panel clamp test).
- No API, wire-format, or dependency changes. The cursor backend and
  transport are untouched — this is a pure pipeline-output change.
- Trade-off: the outermost ~1% of the panel's aim range is no longer
  reachable exactly at the edge; negligible against the accuracy
  figures already documented in README's "Marker visibility and
  accuracy" section.
