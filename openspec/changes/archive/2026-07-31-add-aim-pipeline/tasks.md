## 1. Marker map

- [x] 1.1 Add `src/boresight/marker_map.py` with a `MarkerMap` dataclass
      (screen size in mm, markers keyed by ID) and
      `load_marker_map(path) -> MarkerMap` parsing TOML via `tomllib`
- [x] 1.2 Implement `MarkerMap.corners_mm(marker_id)` returning the four
      screen-mm corners clockwise from top-left `[(x, y), (x + s, y),
      (x + s, y + s), (x, y + s)]`, or `None` for an unknown ID
- [x] 1.3 Implement eager validation with clear, identifying errors:
      missing required field, duplicate marker `id`, non-positive screen
      dimension, non-positive `size_mm`
- [x] 1.4 Add `config/markers.toml` holding the reference layout — the
      1220x686mm panel and the 8 markers (4 corners + 4 edge midpoints,
      80mm) that `tests/generate_synthetic_video_fixture.py` renders
- [x] 1.5 Add `tests/test_marker_map.py`: valid load, per-marker differing
      sizes, bezel coordinates outside the panel accepted, corner order
      and derivation, unknown ID returns `None`, and one test per
      validation error

## 2. Pipeline

- [x] 2.1 Add `src/boresight/pipeline.py` with a `FrameOutcome` enum
      (`SOLVED`, `NO_MARKERS`, `INSUFFICIENT_CORRESPONDENCES`,
      `SOLVE_FAILED`) and a `FrameResult` dataclass carrying outcome,
      `aim_point_mm`, normalized position, `clamped`, detected/mapped/
      ignored marker counts, and the solve's conditioning fields
- [x] 2.2 Implement `AimPipeline(marker_map, backend)` holding only its
      collaborators, with a stateless `process_frame(frame) -> FrameResult`
- [x] 2.3 In `process_frame`: convert a 3-channel frame to grayscale,
      detect markers, and assemble correspondences by pairing each mapped
      marker's detected corners with `corners_mm` positionally
- [x] 2.4 Skip detected markers absent from the map, counting them as
      ignored rather than failing the frame
- [x] 2.5 Normalize the solved aim point against the map's screen size,
      clamp into `[0.0, 1.0]` at the emission boundary, record `clamped`,
      and emit exactly one `move_absolute` per solved frame
- [x] 2.6 Catch `InsufficientCorrespondencesError` and the solver's
      degenerate-homography `ValueError`, convert them to outcomes, and
      emit nothing for unsolved frames
- [x] 2.7 Emit poorly conditioned solves and propagate
      `aim_point_inside_hull` / `aim_point_hull_distance_mm` into the
      result rather than suppressing the move

## 3. Pipeline unit tests

- [x] 3.1 Add `tests/test_pipeline.py` driving `AimPipeline` against a
      `FakeCursorBackend` with synthetic detection input
- [x] 3.2 Cover the emission path: a solvable frame emits exactly one
      move; screen centre normalizes to `(0.5, 0.5)`; two calls on the
      same frame return equal results and emit twice
- [x] 3.3 Cover the no-emission paths: no markers detected, and fewer
      correspondences than a homography needs — each returns the right
      outcome, raises nothing, and leaves the backend untouched
- [x] 3.4 Cover the policy paths: an unmapped marker ID is ignored and
      counted while the frame still solves; an off-panel aim point is
      clamped, emitted, and reported; a flagged solve is emitted with its
      conditioning surfaced

## 4. End-to-end replay

- [x] 4.1 Add a `replay(frames_dir, backend)` helper that reads a fixture
      manifest, runs each frame through `process_frame` in order, and
      returns the per-frame results
- [x] 4.2 Add a `python -m boresight.pipeline <frames-dir>` entry point
      using the real uinput backend, with `--dry-run` swapping in a
      recording backend and printing the track
- [x] 4.3 Add `tests/test_pipeline_e2e.py` replaying
      `tests/fixtures/synthetic_video/` through the real pipeline into a
      `FakeCursorBackend`, asserting emitted normalized positions against
      the manifest ground truth within a documented tolerance derived
      from the existing 4.0mm solver tolerance
- [x] 4.4 Assert in the same file that every video-fixture frame solves,
      that one move is emitted per frame, and that no frame is clamped
- [x] 4.5 Replay `tests/fixtures/close_range/` and assert the run
      completes, that zero-marker poses produce `NO_MARKERS` with no
      emission, and that solvable close-range poses still emit

## 5. Consistency and wiring

- [x] 5.1 Add a test asserting `config/markers.toml` and each fixture
      manifest declare the same screen size, marker IDs, positions and
      sizes
- [x] 5.2 Verify no fixture byte changed (`git status` clean under
      `tests/fixtures/`) and that the full suite still passes, including
      the pre-existing solver tests left untouched

## 6. Documentation and gate

- [x] 6.1 Update README: describe the pipeline and `config/markers.toml`
      as built rather than future work, note that the shipped layout is
      the reference layout the accuracy numbers were measured against,
      document the replay command, and state that filtering and dropout
      decay are still absent
- [x] 6.2 Tick the relevant Milestones entries and adjust "Repo layout"
      so it reflects what now exists
- [x] 6.3 Run `uv run pytest`, `uv run ruff check`, `uv run ruff format
      --check`, and `uv run pre-commit run --all-files` clean
- [x] 6.4 Run `openspec validate add-aim-pipeline --strict`
