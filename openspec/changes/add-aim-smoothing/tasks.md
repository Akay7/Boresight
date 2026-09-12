## 1. The filter

- [ ] 1.1 Add a one-euro filter implementation (2D position, monotonic
      timestamp per update, minimum cutoff frequency and speed
      coefficient as constructor parameters with defaults) and unit
      test it directly: a near-constant input stays close to its mean,
      a fast consistent ramp tracks with little lag, and the first call
      returns its input unchanged
- [ ] 1.2 Test that timing is driven by a monotonic clock rather than
      call count — feeding calls with an explicit, varying `dt` produces
      different smoothing than feeding the same values at a fixed `dt`
- [ ] 1.3 Test that a large `dt` after a gap does not overshoot or sweep
      through intermediate positions — the next value after a gap moves
      toward the new input at least as fast as an equal-`dt` step
      earlier in a steady sequence

## 2. The cursor backend decorator

- [ ] 2.1 Add a `CursorBackend` implementation that wraps another
      `CursorBackend`: `move_absolute` runs `(x, y)` through the filter
      before forwarding the result, `click` forwards unchanged
- [ ] 2.2 Test against a `FakeCursorBackend`: filtered `move_absolute`
      calls reach the wrapped backend already smoothed, and `click`
      calls reach it untouched and don't themselves feed the filter
- [ ] 2.3 Test that `click()` after a filtered move lands at the
      filtered position, not the position that was passed in

## 3. Wiring

- [ ] 3.1 Have `MarkerSourceController` wrap the backend it is given
      once, at its own construction, and pass the wrapped backend to
      every `AimPipeline` it builds — including on a marker-source
      switch
- [ ] 3.2 Test that two `AimPipeline`s built by the same controller
      (e.g. across a switch) share one filter's state rather than each
      starting fresh
- [ ] 3.3 Confirm `server.py`'s `POST /cursor/move` route still uses
      the unwrapped backend from `app.state.cursor_backend`, and add a
      test that a manual move request is unaffected by prior
      aim-derived filter state (moves to exactly the requested
      position regardless of what the filter last saw)

## 4. Integration tests

- [ ] 4.1 Extend the pipeline/marker-source test fixtures to drive
      several frames with small position variation through a real
      `AimPipeline` wired through the wrapped backend, and assert the
      backend's recorded positions vary less than the raw solved
      positions did
- [ ] 4.2 Test that a switch between marker sources mid-sequence, with
      an unchanged underlying aim point, produces no discontinuity in
      the wrapped backend's recorded positions attributable to the
      switch itself

## 5. Manual verification

- [ ] 5.1 On a real device, hold aim on a fixed target and confirm the
      cursor visibly steadies compared to before this change
- [ ] 5.2 On a real device, swing aim quickly to a new target and
      confirm the cursor keeps up without noticeably lagging behind
- [ ] 5.3 Switch marker source mid-stream while holding aim and confirm
      no jump or stutter in cursor position attributable to the switch
- [ ] 5.4 Confirm a trigger press lands where the visibly displayed
      cursor is, not offset from it
- [ ] 5.5 Confirm `curl -X POST /cursor/move` still lands exactly on
      the requested coordinates while aim-derived streaming is active
- [ ] 5.6 Moved from `add-screen-marker-overlay`: confirm the
      fullscreen-exclusive limitation in practice, and that
      borderless-windowed works, so README documents behaviour rather
      than expectation
- [ ] 5.7 Moved from `add-screen-marker-overlay`: on Windows, verify
      the same overlay behaviour — untested by anyone so far, so treat
      the Qt-to-`WS_EX_TRANSPARENT` mapping as a documentation claim
      until someone runs it

## 6. Documentation and gate

- [ ] 6.1 Check off `1-euro filter tuning` in README's milestones list
      and add a short "Aim smoothing" note describing the tradeoff
      (steady aim is smoothed, fast movement is not) and that it does
      not affect `/cursor/move`
- [ ] 6.2 Run `uv run pytest`, `uv run ruff check`, `uv run ruff format
      --check` and `uv run pre-commit run --all-files` clean
- [ ] 6.3 Run `openspec validate add-aim-smoothing --strict`
