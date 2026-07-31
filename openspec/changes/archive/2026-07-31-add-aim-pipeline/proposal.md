## Why

Boresight has three working modules that nothing connects: `detect.py`
finds markers, `solve.py` turns correspondences into a screen-space aim
point, and `inject.py` moves the OS cursor. There is no code path from a
frame to a cursor position, and the piece that would join them — a
marker map turning a detected marker ID into its known screen-plane
corners — does not exist at all. The layout it would provide is instead
duplicated as a hardcoded `MARKER_LAYOUT_MM` dict inside two test
fixture generators.

Closing that gap is small, needs no camera and no new hardware, and
converts the existing Blender fixtures from solver-only tests into
end-to-end coverage of the whole software path.

## What Changes

- Add `config/markers.toml` in the format README already specifies
  (`screen_width_mm`, `screen_height_mm`, and a `[[marker]]` array of
  `id`/`x`/`y`/`size_mm`), populated with the reference layout the
  existing fixtures render.
- Add `src/boresight/marker_map.py`: loads and validates that file into
  a `MarkerMap` that answers "what are marker N's four corners, in
  screen millimetres, in detector corner order?".
- Add `src/boresight/pipeline.py`: given a frame, run detection, pair
  each detected marker's corners with the map's screen-mm corners,
  solve, normalize the aim point against the screen size, and emit it
  to a `CursorBackend`. Stateless and synchronous — one frame in, one
  result out.
- Define the pipeline's policy for the cases `solve.py` deliberately
  leaves to its consumer: too few correspondences, unknown marker IDs,
  an aim point off the panel, and a solve flagged as poorly
  conditioned.
- Add a replay entry point (`python -m boresight.pipeline <frames>`)
  that runs a checked-in frame sequence through the real pipeline, so
  the path is demonstrable against the actual OS cursor without a phone
  or camera.
- Add tests: unit coverage for the map and the pipeline's policy
  branches, plus end-to-end replay of `tests/fixtures/synthetic_video/`
  and `tests/fixtures/close_range/` into a `FakeCursorBackend`,
  asserting the emitted cursor track against each fixture's manifest
  ground truth.
- Add a consistency test asserting `config/markers.toml` and the fixture
  manifests describe the same layout, so the shipped config and the
  rendered scene cannot drift apart silently.

Not in scope, and explicitly deferred: 1-euro filtering, hold-last-good
and decay on dropout, `cornerSubPix`/`undistortPoints`, and any server,
WebSocket, or phone-side video ingest. The pipeline is the seam those
land on later, not this change.

## Capabilities

### New Capabilities
- `marker-map`: the physical marker layout as configuration — file
  format, coordinate convention, validation, and the mapping from a
  detected marker ID to its four screen-plane corners.
- `aim-pipeline`: the composition of detection, marker lookup, solving,
  normalization, and cursor emission into a single per-frame operation,
  including its behaviour when a frame cannot be solved.

### Modified Capabilities
<!-- None. `homography-solve` gains a consumer but no requirement of it
     changes; `cursor-injection` is called through its existing
     `CursorBackend` protocol, which is unchanged. -->

## Impact

- New: `config/markers.toml`, `src/boresight/marker_map.py`,
  `src/boresight/pipeline.py`, and their tests.
- Unchanged: `solve.py`, `detect.py`, `inject.py`, `server.py`. The
  pipeline is a new consumer of existing interfaces, not a modification
  of them — in particular it uses the `CursorBackend` protocol directly
  rather than going through the HTTP endpoint.
- Existing fixtures (`tests/fixtures/synthetic_video/`,
  `tests/fixtures/close_range/`) gain a second reader. They are not
  regenerated; this change must not alter a single fixture byte.
- Dependencies: none added. TOML parsing uses the standard library's
  `tomllib`.
- README: the "Repo layout" and "Milestones" sections describe
  `markers.toml` and the pipeline as future work and will need
  updating.
